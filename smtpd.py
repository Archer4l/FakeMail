import mailparser
import sqlite3
from aiosmtpd.controller import Controller
import os
from datetime import datetime
from web import start_web


class DataHandler(object):

    def __init__(self, mailbox_dir, db_name, table_name):
        self.maildir =os.path.expanduser(mailbox_dir)
        self.db_name = db_name
        self.table_name = table_name
        self.db = f"{self.maildir}/{self.db_name}"
        self.init_db()

    async def save_mail(self, _from, to, email_title, tm, raw_mail, has_attach):
        conn = sqlite3.connect(self.db)
        cur = conn.cursor()
        sql = f"""
            insert into {self.table_name} (`email_from`, `email_to`, `email_title`,  `dt`, `email_raw`, `has_attach`) values
            (?, ?, ?, ?,?, ?)
        """
        #print(sql)
        cur.execute(sql, (_from, to, email_title, tm, raw_mail, has_attach))
        conn.commit()
        cur.close()
        conn.close()

    async def parse(self, from_,to_, raw_mail):
        mail = mailparser.parse_from_string(raw_mail)
        email_subject = mail.subject
        has_attach = 1 if len(mail.attachments)>0 else 0
        tm = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        print(f"{tm}\t{from_}\t{to_}\t{email_subject}")
        for ito_ in to_:
            await self.save_mail(from_, ito_, email_subject,  tm, raw_mail, has_attach)



    async def handle_DATA(self, server, session, envelope):
         from_ = envelope.mail_from
         to_ = envelope.rcpt_tos

         s = envelope.content.decode('utf8', errors='replace')
         await self.parse(from_, to_, s)
         return '250 Message accepted for delivery'

    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
         #if not address.endswith('@example1.com'):
         #    return '550 not relaying to that domain'
         '''
         add checks email
         '''
         envelope.rcpt_tos.append(address)
         return '250 OK'

    # async def handle_DATA(self, server, session, envelope):
    #     print('Message from %s' % envelope.mail_from)
    #     print('Message for %s' % envelope.rcpt_tos)
    #     print('Message data:\n')
    #     print(envelope.content.decode('utf8', errors='replace'))
    #     print('End of message')
    #     return '250 Message accepted for delivery'

    def init_db(self):
        print(f"use db {self.db}")
        conn = sqlite3.connect(self.db)
        cur = conn.cursor()
        sql = f"""
            create table  if not exists  {self.table_name}(
            id INTEGER  PRIMARY KEY autoincrement,
            email_from   VARCHAR(255),
            email_to  VARCHAR(255),
            email_title VARCHAR(512),
            dt TEXT,
            email_raw TEXT,
            has_attach INTEGER not null
            )
        """
        cur.execute(sql)
        conn.commit()
        cur.close()
        conn.close()


if __name__=='__main__':

    try:
        controller = Controller(DataHandler("~/mailbox", 'fake_mail.db', "fake_mail"), hostname='127.0.0.1', port=25)
        controller.start()

        start_web("127.0.0.1", "9080")
    except KeyboardInterrupt:
        print("smtpd quit!")
