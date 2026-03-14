from fastapi import FastAPI, HTTPException
import sqlite3, os
from google import genai
from pydantic import BaseModel
from dotenv import load_dotenv
load_dotenv()

app = FastAPI(title="Movie Recommender API")
client = genai.Client()


import time
last_request_time = 0


def get_db():
    conn = sqlite3.connect('movies.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db = get_db()
    db.execute("CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT)")
    db.execute("""CREATE TABLE IF NOT EXISTS likes(
        id INTEGER PRIMARY KEY, 
        user_id INTEGER,
        title TEXT,
        genre TEXT, 
        year INTEGER)""")
    db.commit()
    db.close()
    
init_db()
    
    
class UserCreate(BaseModel):
    name: str
    
class LikeCreate(BaseModel):
    user_id: int
    title: str
    genre: str = ""
    year: int = 0
    
@app.get("/")
def root():
    return {"message": "Movie Recommender API is running"}
    
@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/movies")
def browse_movies():
        return {"movies": [
        {"title": "Inception", "genre": "Sci-Fi", "year": 2010},
        {"title": "The Godfather", "genre": "Crime", "year": 1972},
        {"title": "Parasite", "genre": "Thriller", "year": 2019},
        {"title": "Interstellar", "genre": "Sci-Fi", "year": 2014},
        {"title": "Spirited Away", "genre": "Animation", "year": 2001},
    ]}
        
@app.post("/users", status_code=201)
def create_user(user: UserCreate):
    db = get_db()
    try:
        db.execute("INSERT INTO users (name) VALUES (?)", (user.name,))
        db.commit()
        user_id = db.execute("SELECT id FROM users WHERE name = ?", (user.name,)).fetchone()["id"]
        return {"user_id": user_id, "name": user.name}
    except sqlite3.IntegrityError:
        raise HTTPException(400, "Username already exists")
    finally:
        db.close()
        
@app.post("/likes", status_code=201)
def add_like(like: LikeCreate):
    db = get_db()
    user = db.execute("SELECT id FROM users WHERE id = ?", (like.user_id,)).fetchone()
    if not user:
        raise HTTPException(404, "User not found")
    db.execute("INSERT INTO likes (user_id, title, genre, year) VALUES (?,?,?,?)", (like.user_id, like.title, like.genre, like.year))
    db.commit()
    db.close()
    return {"message": f"Added {like.title} to liked list", }
    
@app.get("/likes/{user_id}")
def get_likes(user_id:int):
    db = get_db()
    rows = db.execute("SELECT title, genre, year FROM likes WHERE user_id = ?", (user_id,)).fetchall()
    db.close()
    return {"user_id": user_id, "liked_movies": [dict(r) for r in rows]} 

@app.get("/recommendations/{user_id}")
def recommend(user_id: int):
    global last_request_time
    now = time.time()
    if now - last_request_time < 60:
        raise HTTPException(429, "Rate limit exceeded. Please wait a minute before trying again.")
    last_request_time = now
    db = get_db()
    rows = db.execute("SELECT title, genre FROM likes WHERE user_id = ?", (user_id,)).fetchall()
    db.close()
    if not rows:
        raise HTTPException(400, "User has no liked movies yet")
    liked = ", ".join(f"{r['title']} ({r['genre']})" for r in rows)
    prompt = (
        f"A user liked these movies: {liked}. "
        "Recommend 5 movies they would enjoy. "
        "For each, give: title, genre, year, and one sentence why. "
        "Be concise and friendly."
    )
    response = client.models.generate_content(
        model="gemini-3.1-flash-lite-preview",
        contents=prompt,
        )
    return {"user_id": user_id, "recommendations": response.text}