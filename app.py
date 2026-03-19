from flask import Flask, render_template, request, redirect, session
import pandas as pd
import os
import mysql.connector
import bcrypt
from dotenv import load_dotenv

load_dotenv()


app = Flask(__name__)
app.secret_key = "secretkey"

UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ================= DB CONNECTION =================
from db_config import get_db_connection


# ================= INSIGHT FUNCTION =================
def generate_insights(df):
    insights = []

    numeric_cols = df.select_dtypes(include='number').columns

    for col in numeric_cols:
        insights.append(f"Average {col} is {df[col].mean():.2f}")
        insights.append(f"Maximum {col} is {df[col].max()}")
        insights.append(f"Minimum {col} is {df[col].min()}")

    return insights

# ================= SQL GENERATOR =================
def generate_sql_query(user_input, columns=None):
    if not columns:
        columns = []
        
    prompt = f"""
    You are an expert SQL query generator. 
    Table name: `uploaded_csv_data`
    Columns available: {', '.join(columns)}
    
    User request: "{user_input}"
    
    Generate the MySQL query that fulfills this request. 
    Return ONLY the raw SQL query. Do NOT wrap it in markdown block quotes (no ```sql). Do not provide any explanations.
    """
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "your_api_key_here":
        return "-- ERROR: Please add your GEMINI_API_KEY to the .env file!"
        
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        query = response.text.strip()
        # Clean markdown if the model accidentally included it
        if query.startswith("```sql"):
            query = query[6:]
        if query.startswith("```"):
            query = query[3:]
        if query.endswith("```"):
            query = query[:-3]
            
        return query.strip()
    except Exception as e:
        return f"-- The exact error from Google Gemini was:\n-- {str(e)}\n\n-- Please ensure your API key in the .env file is correct and valid."

# ================= ROUTES =================

@app.route('/')
def home():
    return redirect('/login')

# -------- SIGNUP --------
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
            (username, email, hashed_pw)
        )

        conn.commit()
        conn.close()

        return redirect('/login')

    return render_template('signup.html')

# -------- LOGIN --------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = cursor.fetchone()
        conn.close()

        if user:
            db_password = user['password'].encode('utf-8') if isinstance(user['password'], str) else bytes(user['password'])
            if bcrypt.checkpw(password.encode('utf-8'), db_password):
                session['user'] = user['username']
                return redirect('/dashboard')

    return render_template('login.html')

# -------- DASHBOARD --------
@app.route('/dashboard', methods=['GET'])
def dashboard():
    if 'user' not in session:
        return redirect('/login')

    return render_template('dashboard.html', user=session['user'])

# -------- INSIGHTS --------
@app.route('/insights', methods=['GET', 'POST'])
def insights():
    if 'user' not in session:
        return redirect('/login')

    insights_data = []

    if request.method == 'POST':
        file = request.files['file']
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(filepath)

        df = pd.read_csv(filepath)
        insights_data = generate_insights(df)

    return render_template('insights.html', insights=insights_data)

# -------- SQL GENERATOR --------
@app.route('/sql-generator', methods=['GET', 'POST'])
def sql_generator():
    if 'user' not in session:
        return redirect('/login')

    query = ""
    filename = session.get('last_filename', None)
    columns_str = session.get('last_columns', "")

    if request.method == 'POST':
        user_input = request.form['input']
        
        file = request.files.get('file')
        if file and file.filename != '':
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(filepath)
            df = pd.read_csv(filepath)
            columns_list = df.columns.tolist()
            filename = file.filename
            columns_str = ", ".join(columns_list)
            
            session['last_filename'] = filename
            session['last_columns'] = columns_str
            
        columns_list = [c.strip() for c in columns_str.split(",")] if columns_str else []

        base_query = generate_sql_query(user_input, columns_list)
        query = f"-- Detected Context Columns: {columns_str}\n{base_query}"

    return render_template('sql_generator.html', query=query, filename=filename)

# -------- LOGOUT --------
@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/login')

if __name__ == '__main__':
    app.run(debug=True)