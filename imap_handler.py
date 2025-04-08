"""
Imap Handler module.

This module is part of the Personal Mail Server project.
"""

# imap_handler.py
import logging
import asyncio
from typing import List, Dict, Optional, Tuple
import bcrypt
from sqlalchemy import select
from models import User

logger = logging.getLogger(__name__)

class IMAPResponse:
    def __init__(self, status: str, data: List[str] = None):
        self.status = status
        self.data = data or []

    def encode(self) -> bytes:
        response = []
        for line in self.data:
            response.append(f"* {line}\r\n")
        response.append(f"{self.status}\r\n")
        return "".join(response).encode()

class IMAPProtocol(asyncio.Protocol):
    def __init__(self, config, storage, session_factory):
        self.config = config
        self.storage = storage
        self.session_factory = session_factory
        self.transport = None
        self.buffer = ""
        self.authenticated_users = {}
        self.current_user = None
        self.selected_mailbox = None

    def connection_made(self, transport):
        self.transport = transport
        self.send_response("OK", ["Server ready"])

    def data_received(self, data):
        self.buffer += data.decode()
        if "\r\n" in self.buffer:
            command, self.buffer = self.buffer.split("\r\n", 1)
            asyncio.create_task(self.handle_command(command))

    def send_response(self, status: str, data: List[str] = None):
        response = IMAPResponse(status, data)
        self.transport.write(response.encode())

    async def handle_command(self, command: str):
        try:
            parts = command.split()
            if not parts:
                return
            
            tag, cmd, *args = parts
            cmd = cmd.upper()

            if cmd == "LOGIN":
                await self.handle_login(tag, *args)
            elif cmd == "LIST":
                await self.handle_list(tag, *args)
            elif cmd == "SELECT":
                await self.handle_select(tag, *args)
            elif cmd == "FETCH":
                await self.handle_fetch(tag, *args)
            elif cmd == "LOGOUT":
                await self.handle_logout(tag)
            else:
                self.send_response(f"{tag} BAD Unknown command")
        except Exception as e:
            logger.error(f"Command handling error: {str(e)}")
            self.send_response(f"{tag} NO Error processing command")

    async def handle_login(self, tag: str, username: str, password: str):
        try:
            async with self.session_factory() as session:
                result = await session.execute(
                    select(User).where(User.email == username)
                )
                user = result.scalar_one_or_none()
                
                if user and bcrypt.checkpw(password.encode(), user.password_hash.encode()):
                    self.authenticated_users[username] = True
                    self.current_user = username
                    self.send_response(f"{tag} OK", ["Logged in successfully"])
                else:
                    self.send_response(f"{tag} NO", ["Invalid credentials"])
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            self.send_response(f"{tag} NO", ["Server error"])

    async def handle_list(self, tag: str, reference: str, mailbox: str):
        if not self.current_user:
            self.send_response(f"{tag} NO Not authenticated")
            return

        folders = ['INBOX', 'Sent', 'Trash', 'Drafts', 'Spam']
        response = []
        for folder in folders:
            response.append(f'LIST (\\HasNoChildren) "/" {folder}')
        self.send_response(f"{tag} OK", response)

    async def handle_select(self, tag: str, mailbox: str):
        if not self.current_user:
            self.send_response(f"{tag} NO Not authenticated")
            return

        try:
            async with self.session_factory() as session:
                emails = await self.storage.get_emails(session, self.current_user, mailbox)
                uidnext = max([e['uid'] for e in emails], default=1000) + 1
                
                response = [
                    f"{len(emails)} EXISTS",
                    "0 RECENT",
                    f"OK [UIDVALIDITY 1]",
                    f"OK [UIDNEXT {uidnext}]",
                    "FLAGS (\\Seen \\Answered \\Flagged \\Deleted \\Draft)",
                    "OK [PERMANENTFLAGS (\\Seen \\Answered \\Flagged \\Deleted \\Draft \\*)]"
                ]
                self.selected_mailbox = mailbox
                self.send_response(f"{tag} OK", response)
        except Exception as e:
            logger.error(f"Select error: {str(e)}")
            self.send_response(f"{tag} NO Server error")

    async def handle_fetch(self, tag: str, sequence_set: str, *args):
        if not self.current_user or not self.selected_mailbox:
            self.send_response(f"{tag} NO Not authenticated or no mailbox selected")
            return

        try:
            async with self.session_factory() as session:
                emails = await self.storage.get_emails(
                    session, self.current_user, self.selected_mailbox)
                response = []
                
                for email in emails:
                    decrypted_content = self.config.cipher_suite.decrypt(
                        email['content'].encode('utf-8'))
                    response.append(
                        f"{email['uid']} FETCH ("
                        f"UID {email['uid']} "
                        f"FLAGS ({' '.join(email['flags'].split())}) "
                        f"BODY[] {{{len(decrypted_content)}}}\r\n{decrypted_content}"
                        f")"
                    )
                
                self.send_response(f"{tag} OK", response)
        except Exception as e:
            logger.error(f"Fetch error: {str(e)}")
            self.send_response(f"{tag} NO Server error")

    async def handle_logout(self, tag: str):
        if self.current_user in self.authenticated_users:
            del self.authenticated_users[self.current_user]
        self.current_user = None
        self.selected_mailbox = None
        self.send_response(f"{tag} OK", ["BYE IMAP4rev1 Server logging out"])
        self.transport.close()

def create_imap_server(config, storage, session_factory):
    def protocol_factory():
        return IMAPProtocol(config, storage, session_factory)
    
    return protocol_factory