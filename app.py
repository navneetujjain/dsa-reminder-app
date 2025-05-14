import os
from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from authlib.integrations.flask_client import OAuth
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///dsa.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db = SQLAlchemy(app)
oauth = OAuth(app)

# Configure Google OAuth
oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    access_token_url='https://accounts.google.com/o/oauth2/token',
    access_token_params=None,
    authorize_url='https://accounts.google.com/o/oauth2/auth',
    authorize_params=None,
    api_base_url='https://www.googleapis.com/oauth2/v1/',
    client_kwargs={'scope': 'openid email profile'},
)

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    questions = db.relationship('Question', backref='user', lazy=True)

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    link = db.Column(db.String(500))
    date_added = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

# Email Sending Function
def send_reminder_email(user_email, questions):
    message = Mail(
        from_email='dsa-reminder@example.com',
        to_emails=user_email,
        subject='📚 Your Daily DSA Revision Reminder')
    
    content = "<h1>Questions to Revise Today:</h1><ul>"
    for q in questions:
        content += f"<li>{q.name}"
        if q.link:
            content += f" <a href='{q.link}'>Link</a>"
        content += "</li>"
    content += "</ul>"
    
    message.add_content(content, "text/html")
    
    try:
        sg = SendGridAPIClient(os.getenv('SENDGRID_API_KEY'))
        response = sg.send(message)
    except Exception as e:
        print(f"Email error: {str(e)}")

# Scheduled Job
def daily_reminder_job():
    with app.app_context():
        target_dates = [datetime.utcnow() - timedelta(days=d) for d in [3,7,15]]
        
        for user in User.query.all():
            questions = Question.query.filter(
                Question.user_id == user.id,
                db.func.date(Question.date_added).in_([d.date() for d in target_dates])
            ).all()
            
            if questions:
                send_reminder_email(user.email, questions)

# Initialize scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(daily_reminder_job, 'cron', hour=4, minute=30)  # 10am IST = 4:30 UTC
scheduler.start()

# Routes
@app.route('/')
def home():
    if 'user' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user']['id'])
    return render_template('index.html', user=user)

@app.route('/login')
def login():
    redirect_uri = url_for('authorize', _external=True)
    print(f"Using redirect URI: {redirect_uri}")
    return oauth.google.authorize_redirect(redirect_uri)

@app.route('/authorize')
def authorize():
    token = oauth.google.authorize_access_token()
    user_info = oauth.google.get('userinfo').json()
    
    user = User.query.filter_by(email=user_info['email']).first()
    if not user:
        user = User(email=user_info['email'])
        db.session.add(user)
        db.session.commit()
    
    session['user'] = {'id': user.id, 'email': user.email}
    return redirect(url_for('home'))

@app.route('/add', methods=['POST'])
def add_question():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    new_question = Question(
        name=request.form['name'],
        link=request.form.get('link'),
        user_id=session['user']['id']
    )
    db.session.add(new_question)
    db.session.commit()
    return redirect(url_for('home'))

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('home'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)