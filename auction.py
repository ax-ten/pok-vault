
import logging
import sqlite3
from datetime import datetime, timedelta
from enum import Enum

class Valuta(Enum):
    Pokédollari = "₽"


class AuctionDB:
    DB_PATH = 'auction_bot.db'

    

    @staticmethod
    def initialize_db():
        conn = sqlite3.connect(AuctionDB.DB_PATH)
        cursor = conn.cursor()

        # Creazione delle tabelle se non esistono già
        cursor.execute('''CREATE TABLE IF NOT EXISTS active_auctions (
                            id           INTEGER PRIMARY KEY AUTOINCREMENT,
                            card_name    TEXT,
                            last_bid     INTEGER,
                            user_id      TEXT,
                            message_id   TEXT)''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS archived_auctions (
                            id           INTEGER PRIMARY KEY AUTOINCREMENT,
                            card_name    TEXT,
                            paid         INTEGER,
                            user_id      INTEGER)''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                            user_id      INTEGER PRIMARY KEY,
                            user_name    TEXT,
                            wallet       INTEGER)''')
        

        cursor.execute('''CREATE TABLE IF NOT EXISTS gift_claims (
                            gift_id       INTEGER,
                            user_id       INTEGER,
                            UNIQUE(gift_id, user_id) ON CONFLICT IGNORE)''')
    

        conn.commit()
        conn.close()

    @staticmethod
    def add_active_auction(card_name, message_id):
        conn = sqlite3.connect(AuctionDB.DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO active_auctions (card_name, last_bid, user_id, message_id) VALUES (?, ?, ?, ?)",
            (card_name, 0, None, message_id)
        )
        conn.commit()
        conn.close()

    @staticmethod
    def update_bid(auction_id, new_bid, user_id):
        conn = sqlite3.connect(AuctionDB.DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE active_auctions SET last_bid = ?, user_id = ? WHERE id = ?",
            (new_bid, user_id, auction_id)
        )
        conn.commit()
        conn.close()


    @staticmethod
    def end_auction(auction_id: int) -> str:
        """Termina l'asta specificata e determina il vincitore, se presente."""
        conn = sqlite3.connect(AuctionDB.DB_PATH)
        cursor = conn.cursor()

        # Verifica se l'asta è attiva
        cursor.execute("SELECT id, card_name, last_bid, user_id FROM active_auctions WHERE id = ?", (auction_id,))
        auction = cursor.fetchone()

        if not auction:
            conn.close()
            return "L'asta specificata non è attiva o non esiste."

        auction_id, card_name, last_bid, user_id = auction

        # Se non ci sono offerte (last_bid è 0), nessun vincitore
        if last_bid == 0:
            result = f"L'asta per {card_name} è terminata senza offerte."
            AuctionDB.archive_auction(auction_id)  # Archivia l'asta prima di eliminarla
        else:
            # Determina il vincitore
            winner = AuctionDB.name_of_user(user_id)
            result = f"{winner} si è aggiudicatə {card_name} per {last_bid}{Valuta.Pokédollari.value}!"

            # Archivia l'asta e aggiorna il campo `paid` in `archived_auctions`
            AuctionDB.archive_auction(auction_id)
            cursor.execute("UPDATE archived_auctions SET paid = ? WHERE id = ?", (last_bid, auction_id))

            # Aggiorna il saldo dell'utente vincitore nella tabella users
            cursor.execute("UPDATE users SET wallet = wallet - ? WHERE user_id = ?", (last_bid, user_id))

        conn.commit()
        conn.close()
        return result

    @staticmethod
    def archive_auction(auction_id):
        """Archivia l'asta con l'ID specificato."""
        conn = sqlite3.connect(AuctionDB.DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO archived_auctions (id, card_name, paid, user_id) "
            "SELECT id, card_name, 0, user_id FROM active_auctions WHERE id = ?",
            (auction_id,)
        )
        cursor.execute("DELETE FROM active_auctions WHERE id = ?", (auction_id,))
        conn.commit()
        conn.close()

    @staticmethod
    def get_active_auctions(message_id=None):
        conn = sqlite3.connect(AuctionDB.DB_PATH)
        cursor = conn.cursor()
        
        if message_id is not None:
            auctions = cursor.execute("""
                SELECT id, card_name, last_bid, user_id 
                FROM active_auctions 
                WHERE message_id = ?
                """,(message_id,)
            ).fetchall()
        else:
            auctions = cursor.execute("""
                SELECT id, card_name, last_bid , user_id 
                FROM active_auctions
                """).fetchall()
        conn.close()
        return auctions
    
    @staticmethod
    def get_auction_by_card_name(card_name: str):
        """Ottiene i dettagli di un'asta attiva in base al nome della carta."""
        conn = sqlite3.connect(AuctionDB.DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, last_bid FROM active_auctions WHERE card_name = ?",
            (card_name,)
        )
        auction = cursor.fetchone() 
        conn.close()
        return auction if auction else None
    
    
    @staticmethod
    def name_of_user(id):
        conn = sqlite3.connect(AuctionDB.DB_PATH)
        cursor = conn.cursor()
        user_name = cursor.execute(
            "SELECT user_name FROM users WHERE user_id = ?",
            (id,)
        ).fetchone()
        conn.commit()
        conn.close()
        return user_name[0]

    
    @staticmethod
    def id_of_user(username):
        conn = sqlite3.connect(AuctionDB.DB_PATH)
        cursor = conn.cursor()
        user_id = cursor.execute(
            "SELECT user_id FROM users WHERE user_name = ?",
            (username,)
        ).fetchone()
        conn.commit()
        conn.close()
        return user_id[0]

    @staticmethod
    def get_user_balance(user_id):
        conn = sqlite3.connect(AuctionDB.DB_PATH)
        cursor = conn.cursor()
        row = cursor.execute(
            "SELECT wallet FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        conn.close()
        return row[0] if row else None


    @staticmethod
    def set_user_balance(user_id, amount):
        conn = sqlite3.connect(AuctionDB.DB_PATH)
        conn.cursor().execute(
            "UPDATE users SET wallet = ? WHERE user_id = ?",
            (amount, user_id)
        )

        conn.commit()
        conn.close()

    @staticmethod
    def add_gift(gift_id):
        conn = sqlite3.connect(AuctionDB.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO gift_claims (gift_id) VALUES (?)", (gift_id,))
        conn.commit()
        conn.close()

    # Funzione per riscattare il gift
    @staticmethod
    def claim_gift(gift_id, user_id):
        conn = sqlite3.connect(AuctionDB.DB_PATH)
        cursor = conn.cursor()

        # Controlla se l'utente ha già riscosso il gift
        cursor.execute("SELECT 1 FROM gift_claims WHERE gift_id = ? AND user_id = ?", (gift_id, user_id))
        already_claimed = cursor.fetchone()

        if already_claimed:
            conn.close()
            return False  # Già riscosso

        # Altrimenti, registra la riscossione
        cursor.execute("INSERT INTO gift_claims (gift_id, user_id) VALUES (?, ?)", (gift_id, user_id))
        conn.commit()
        conn.close()
        return True  # Riscossione riuscita
    

    @staticmethod
    def get_all_balances():
        conn = sqlite3.connect(AuctionDB.DB_PATH)
        cursor = conn.cursor()
        rows = cursor.execute(
            "SELECT user_name, wallet FROM users"
        ).fetchall()
        conn.close()
        return rows

    @staticmethod
    def add_to_wallet(user_id: str, username: str, amount: int) -> int:
        conn = sqlite3.connect(AuctionDB.DB_PATH)
        cursor = conn.cursor()
        wallet = cursor.execute(
            "SELECT wallet FROM users WHERE user_id = ?", 
            (user_id,)
        ).fetchone()

        if not wallet:
            # Inserisce un nuovo record per il nuovo utente
            cursor.execute(
                "INSERT INTO users (user_id, user_name, wallet) VALUES (?, ?, ?)", 
                (user_id, username, amount)
            )
            new_balance = amount
        else:
            # Aggiorna il portafoglio esistente
            new_balance = wallet[0] + amount
            cursor.execute(
                "UPDATE users SET wallet = ? WHERE user_id = ?", 
                (new_balance, user_id)
            )
        
        conn.commit()
        conn.close()
        return new_balance
