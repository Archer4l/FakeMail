# FakeMail
apt install sqlite3
pip3 install -r requirements.txt
python3 smtpd.py

env:
FAKEMAIL_DIR        ~/mailbox
FAKEMAIL_SMTP_HOST  127.0.0.1
FAKEMAIL_SMTP_PORT  25
FAKEMAIL_WEB_HOST   127.0.0.1
FAKEMAIL_WEB_PORT   9080
