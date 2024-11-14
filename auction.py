
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
                            id          INTEGER PRIMARY KEY AUTOINCREMENT,
                            card_name   TEXT,
                            last_bid    INTEGER,
                            bidder_id   INTEGER,
                            closing_time TIMESTAMP)''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS archived_auctions (
                            id          INTEGER PRIMARY KEY AUTOINCREMENT,
                            card_name   TEXT,
                            paid        INTEGER,
                            bidder_id   INTEGER)''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                            bidder_id   INTEGER PRIMARY KEY,
                            bidder_name TEXT,
                            bidder_wallet INTEGER,
                            last_bid_id INTEGER)''')

        conn.commit()
        conn.close()

    @staticmethod
    def add_active_auction(card_name):
        conn = sqlite3.connect(AuctionDB.DB_PATH)
        cursor = conn.cursor()
        closing_time = datetime.now() + timedelta(minutes=30)
        cursor.execute(
            "INSERT INTO active_auctions (card_name, last_bid, bidder_id, closing_time) VALUES (?, ?, ?, ?)",
            (card_name, 0, None, closing_time)
        )
        conn.commit()
        conn.close()

    @staticmethod
    def update_bid(auction_id, new_bid, bidder_id):
        conn = sqlite3.connect(AuctionDB.DB_PATH)
        cursor = conn.cursor()
        closing_time = datetime.now() + timedelta(minutes=30)
        cursor.execute(
            "UPDATE active_auctions SET last_bid = ?, bidder_id = ?, closing_time = ? WHERE id = ?",
            (new_bid, bidder_id, closing_time, auction_id)
        )
        cursor.execute(
            "UPDATE users SET last_bid_id = ? WHERE bidder_id = ?",
            (auction_id, bidder_id)
        )
        conn.commit()
        conn.close()

    @staticmethod
    def archive_auction(auction_id):
        conn = sqlite3.connect(AuctionDB.DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO archived_auctions (id, card_name, paid, bidder_id) "
            "SELECT id, card_name, 0, bidder_id FROM active_auctions WHERE id = ?",
            (auction_id,)
        )
        cursor.execute("DELETE FROM active_auctions WHERE id = ?", (auction_id,))
        conn.commit()
        conn.close()

    @staticmethod
    def get_active_auction(card_name):
        conn = sqlite3.connect(AuctionDB.DB_PATH)
        cursor = conn.cursor()
        auction =cursor.execute("SELECT id, last_bid FROM active_auctions WHERE card_name = ?", (card_name,)).fetchone()
        conn.close()
        return auction

    @staticmethod
    def get_user_balance(bidder_id):
        conn = sqlite3.connect(AuctionDB.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT bidder_wallet FROM users WHERE bidder_id = ?", (bidder_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

    @staticmethod
    def update_user_balance(bidder_id, amount):
        conn = sqlite3.connect(AuctionDB.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET bidder_wallet = ? WHERE bidder_id = ?", (amount, bidder_id))
        conn.commit()
        conn.close()

    @staticmethod
    def set_user_balance(bidder_id, bidder_name, amount):
        conn = sqlite3.connect(AuctionDB.DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO users (bidder_id, bidder_name, bidder_wallet, last_bid_id) VALUES (?, ?, ?, ?)",
            (bidder_id, bidder_name, amount, None)
        )
        conn.commit()
        conn.close()

    @staticmethod
    def add_to_wallet(user_id: int, amount: int) -> bool:
        conn = sqlite3.connect(AuctionDB.DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT bidder_wallet FROM users WHERE bidder_id = ?", (user_id,))
        wallet = cursor.fetchone()

        if not wallet:
            # se non hai wallet, lo inizializza con amount
            cursor.execute("INSERT INTO users (bidder_id, bidder_wallet) VALUES (?, ?)", (user_id, amount))

        # da de-commentare se si vogliono fare gift reali, ma bisogna fare in modo che siano applicabili solo una volta
        # else:
        #     amount = wallet[0] + amount
        #     cursor.execute("UPDATE users SET bidder_wallet = ? WHERE bidder_id = ?", (amount, user_id))
        
        conn.commit()
        conn.close()
        return amount

def close_expired_auctions():
    # Trova tutte le aste che sono scadute (30 minuti senza offerte)
    conn = sqlite3.connect(AuctionDB.DB_PATH)
    cursor = conn.cursor()

    # Seleziona le aste che sono scadute
    expired_auctions = cursor.execute("""
            SELECT id, card_name, last_bid, bidder_id, closing_time
            FROM active_auctions
            WHERE closing_time <= ?
        """, (datetime.now() - timedelta(minutes=30),)
        ).fetchall()

    for auction in expired_auctions:
        auction_id, card_name, last_bid, bidder_id, closing_time = auction

        # Chiudi l'asta, archiviandola e rimuovendola dalla lista attiva
        cursor.execute(
            "INSERT INTO archived_auctions (id, card_name, bidder_id, closing_time) VALUES (?, ?, ?, ?)",
            (auction_id, card_name, bidder_id, closing_time)
        )
        cursor.execute("DELETE FROM active_auctions WHERE id = ?", (auction_id,))
        conn.commit()

        # Dedurre il saldo dell'utente
        if bidder_id:
            wallet = cursor.execute(
                "SELECT bidder_wallet FROM users WHERE bidder_id = ?",
                (bidder_id,)
            ).fetchone()
            
            if wallet and wallet[0] >= last_bid:
                new_balance = wallet[0] - last_bid
                cursor.execute(
                    "UPDATE users SET bidder_wallet = ? WHERE bidder_id = ?",
                    (new_balance, bidder_id)
                )
                conn.commit()


    conn.close()
    return bidder_id, last_bid, card_name
