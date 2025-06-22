from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import date, timedelta
import pytz
import os
from config import Config
from sqlalchemy import text
from datetime import datetime
import atexit
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
app.config.from_object(Config)

logging.basicConfig(
    level=app.config['LOG_LEVEL'],
    format='[%(asctime)s] %(levelname)s: %(message)s'
)

db = SQLAlchemy()
db.init_app(app)

def get_ist_today():
    ist = pytz.timezone('Asia/Kolkata')
    return datetime.now(ist).date()

# Models
class DSAQuestion(db.Model):
    __tablename__ = 'dsa_questions'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    question_name = db.Column(db.String(200), nullable=False)
    question_link = db.Column(db.String(300))
    created_at = db.Column(db.Date, default=get_ist_today)
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

#This was for 18 May, 25 May Testing, successfully tested, everything is fine.
'''@app.route('/test-scheduler')
def test_scheduler():
    with app.app_context():
        check_and_send_reminders()
    return "Scheduler test complete"
'''




# Email sending function
def send_consolidated_email(email, questions, today):
    ist = pytz.timezone('Asia/Kolkata')
    current_time = datetime.now(ist)
    
    app.logger.info(f"[{current_time}] Starting email send to {email}")
    app.logger.debug(f"Processing questions: {questions}")
    
    try:
        # Build email content
        subject = "Revision Reminders"
        html_content = "<h2>Your pending revision Topics/Questions:</h2>"
        
        for reminder_type, q_list in questions.items():
            if q_list:
                days = int(reminder_type.split("_")[0])
                app.logger.info(f"Preparing {days}-day reminders ({len(q_list)} questions)")
                html_content += f"<h3>Due {days}-day reminders:</h3><ul>"
                for q in q_list:
                    html_content += f"<li>{q.question_name}"
                    if q.question_link:
                        html_content += f' (<a href="{q.question_link}">Link</a>)'
                    html_content += "</li>"
                html_content += "</ul>"
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = app.config['MAIL_DEFAULT_SENDER']
        msg['To'] = email
        msg.attach(MIMEText(html_content, 'html'))
        
        app.logger.debug(f"Email payload prepared for {email}")
        
        # Send via SES SMTP
        with smtplib.SMTP(
            host=app.config['MAIL_SERVER'],
            port=app.config['MAIL_PORT']
        ) as server:
            server.starttls()
            server.login(
                user=app.config['MAIL_USERNAME'],
                password=app.config['MAIL_PASSWORD']
            )
            server.send_message(msg)
        
        app.logger.info(f"[{current_time}] Email sent to {email} via AWS SES")
        
        # Mark all as reminded
        for q_list in questions.values():
            for q in q_list:
                if "3_days" in questions and q in questions["3_days"]:
                    q.reminded_3_days = True
                if "7_days" in questions and q in questions["7_days"]:
                    q.reminded_7_days = True
                if "15_days" in questions and q in questions["15_days"]:
                    q.reminded_15_days = True
        
        return True
        
    except Exception as e:
        app.logger.error(f"[{current_time}] AWS SES email failed: {str(e)}")
        raise

# Scheduled job
def check_and_send_reminders():
    with app.app_context():  # Critical: Ensures database access works
        app.logger.info(f"[{datetime.now(pytz.timezone('Asia/Kolkata'))}] Inside check and send reminders")
        try:
            app.logger.info(f"\n[{datetime.now()}] Starting reminder job")
            today = datetime.now(pytz.timezone('Asia/Kolkata')).date()
            users = {}

            # Group questions by email and reminder type
            for question in DSAQuestion.query.all():
                if question.email not in users:
                    users[question.email] = {
                        "3_days": [],
                        "7_days": [],
                        "15_days": []
                    }

                # Check 3-day reminders
                if (not question.reminded_3_days and 
                    question.created_at <= today - timedelta(days=3)):
                    users[question.email]["3_days"].append(question)

                # Check 7-day reminders
                if (not question.reminded_7_days and 
                    question.created_at <= today - timedelta(days=7)):
                    users[question.email]["7_days"].append(question)

                # Check 15-day reminders
                if (not question.reminded_15_days and 
                    question.created_at <= today - timedelta(days=15)):
                    users[question.email]["15_days"].append(question)

            # Send consolidated emails
            for email, questions in users.items():
                if any(questions.values()):  # Only if reminders exist
                    app.logger.info(f"[{datetime.now(pytz.timezone('Asia/Kolkata'))}] Send Consolidated Emails is going to get called")
                    send_consolidated_email(email, questions, today)
                    
                    # Update reminder flags after sending
                    for q_list in questions.values():
                        for question in q_list:
                            if q_list is questions["3_days"]:
                                question.reminded_3_days = True
                            elif q_list is questions["7_days"]:
                                question.reminded_7_days = True
                            elif q_list is questions["15_days"]:
                                question.reminded_15_days = True

            db.session.commit()
            app.logger.info(f"Successfully processed reminders at {datetime.now(pytz.timezone('Asia/Kolkata'))}")

        except Exception as e:
            db.session.rollback()
            app.logger.critical(f"Reminder job crashed: {str(e)}")
            raise

# Initialize scheduler
scheduler = BackgroundScheduler(timezone=pytz.timezone(app.config['TIMEZONE']))
scheduler.add_job(
    check_and_send_reminders,
    'cron',
    hour=10,
    minute=0,
    timezone='Asia/Kolkata'  # 10 AM IST
)
scheduler.start()

atexit.register(lambda: scheduler.shutdown()) #Ensure graceful closure and clean start of scheduler




# Create database tables
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    # Only for local development
    app.run(debug=True)
else:
    # For production (Render/Gunicorn)
    gunicorn_app = app
