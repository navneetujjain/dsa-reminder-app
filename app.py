from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import date, timedelta
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import pytz
import os
from config import Config
from sqlalchemy import text

app = Flask(__name__)
app.config.from_object(Config)

db = SQLAlchemy()
db.init_app(app)

# Models
class DSAQuestion(db.Model):
    __tablename__ = 'dsa_questions'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    question_name = db.Column(db.String(200), nullable=False)
    question_link = db.Column(db.String(300))
    created_at = db.Column(db.Date, default=date.today)
    reminded_3_days = db.Column(db.Boolean, default=False)
    reminded_7_days = db.Column(db.Boolean, default=False)
    reminded_15_days = db.Column(db.Boolean, default=False)

# Routes
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        email = request.form['email']
        question_name = request.form['question_name']
        question_link = request.form.get('question_link', '')

        if not email or not question_name:
            flash('Email and Question Name are required!', 'danger')
            return redirect(url_for('index'))

        new_question = DSAQuestion(
            email=email,
            question_name=question_name,
            question_link=question_link
        )
        db.session.add(new_question)
        db.session.commit()

        flash('Question added successfully! You will receive reminders.', 'success')
        return redirect(url_for('success'))

    return render_template('index.html')

@app.route('/success')
def success():
    return render_template('success.html')

@app.route("/ping")
def ping():
    return "pong", 200

@app.route('/debug-db')
def debug_db():
    from tabulate import tabulate
    results = db.session.execute(text("SELECT * FROM dsa_questions LIMIT 10")).fetchall()
    return f"<pre>{tabulate(results)}</pre>"

@app.route('/test-scheduler')
def test_scheduler():
    with app.app_context():
        check_and_send_reminders()
    return "Scheduler test complete"



# Email sending function
def send_consolidated_email(email, questions, today):
    subject = "DSA Revision Reminders"
    content = "<h2>Your pending DSA revisions:</h2>"
    
    for reminder_type, q_list in questions.items():
        if q_list:
            days = int(reminder_type.split("_")[0])
            content += f"<h3>Due {days}-day reminders:</h3><ul>"
            for q in q_list:
                content += f"<li>{q.question_name}"
                if q.question_link:
                    content += f' (<a href="{q.question_link}">Link</a>)'
                content += "</li>"
            content += "</ul>"
    
    message = Mail(
        from_email=app.config['SENDER_EMAIL'],
        to_emails=email,
        subject=subject,
        html_content=content
    )
    
    try:
        sg = SendGridAPIClient(app.config['SENDGRID_API_KEY'])
        sg.send(message)
        
        # Mark all as reminded
        for q_list in questions.values():
            for q in q_list:
                if "3_days" in questions and q in questions["3_days"]:
                    q.reminded_3_days = True
                if "7_days" in questions and q in questions["7_days"]:
                    q.reminded_7_days = True
                if "15_days" in questions and q in questions["15_days"]:
                    q.reminded_15_days = True
                    
    except Exception as e:
        print(f"Error sending to {email}: {str(e)}")

# Scheduled job
def check_and_send_reminders():
    today = date.today()
    users = {}

    # Group questions by email and reminder type
    for question in DSAQuestion.query.all():
        if question.email not in users:
            users[question.email] = {"3_days": [], "7_days": [], "15_days": []}
        
        if not question.reminded_3_days and question.created_at <= today - timedelta(days=3):
            users[question.email]["3_days"].append(question)
        
        if not question.reminded_7_days and question.created_at <= today - timedelta(days=7):
            users[question.email]["7_days"].append(question)
        
        if not question.reminded_15_days and question.created_at <= today - timedelta(days=15):
            users[question.email]["15_days"].append(question)

    # Send one consolidated email per user
    for email, questions in users.items():
        if any(questions.values()):  # Only if there are pending reminders
            send_consolidated_email(email, questions, today)
    
    db.session.commit()

# Initialize scheduler
#scheduler = BackgroundScheduler(timezone=pytz.timezone(app.config['TIMEZONE']))
#scheduler.add_job(check_and_send_reminders, 'cron', hour=10, minute=0)  # 10 AM IST
#scheduler.start()

def init_scheduler():
    scheduler = BackgroundScheduler(timezone=pytz.timezone(app.config['TIMEZONE']))
    
    def job_with_context():
        with app.app_context():
            try:
                check_and_send_reminders()
                app.logger.info("Successfully ran reminders job")
            except Exception as e:
                app.logger.error(f"Reminder job failed: {str(e)}")
    
    scheduler.add_job(
        job_with_context,
        'cron',
        hour=10,
        minute=0,
        timezone='Asia/Kolkata'
    )
    scheduler.start()

with app.app_context():
    init_scheduler()


# Create database tables
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    # Only for local development
    app.run(debug=True)
else:
    # For production (Render/Gunicorn)
    gunicorn_app = app

