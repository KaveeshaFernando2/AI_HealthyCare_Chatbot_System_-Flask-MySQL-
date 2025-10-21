from flask import Flask, request, jsonify, render_template, redirect
import mysql.connector
import pdfplumber
import json
import re
from datetime import date

app = Flask(__name__)

# ---- JSON-based User Memory ----
def load_user_data():
    try:
        with open("user_data.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_user_data(data):
    with open("user_data.json", "w") as f:
        json.dump(data, f, indent=2)

# ---- MySQL Database Configuration ----
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'database': 'hospital'
}

# ---- Load Doctor Info from JSON ----
def load_doctors():
    with open('doctors.json', 'r') as f:
        return json.load(f)

def search_doctor_info(query):
    doctors = load_doctors()
    query = query.lower()

    # Keyword to specialization mapping (you can expand this)
    keyword_map = {
        "heart": "cardiologist",
        "skin": "dermatologist",
        "teeth": "dentist",
        "eye": "ophthalmologist",
        "bone": "orthopedic",
        "child": "pediatrician",
        "lung": "pulmonologist",
        "diabetes": "endocrinologist"
    }

    # Check for doctor name or specialization in query
    for doctor in doctors:
        name = doctor['name'].lower()
        specialization = doctor['specialization'].lower()

        if name in query or specialization in query:
            return f"{doctor['name']} ({doctor['specialization']}) is available at {doctor['available_time']}."

    # Match using keywords
    for keyword, mapped_specialization in keyword_map.items():
        if keyword in query:
            for doctor in doctors:
                if mapped_specialization in doctor['specialization'].lower():
                    return f"{doctor['name']} ({doctor['specialization']}) is available at {doctor['available_time']}."

    return None


# ---- PDF Search ----
def extract_keywords(query):
    stopwords = {"what", "is", "are", "the", "a", "an", "about", "tell", "me", "explain", "who", "define", "please", "do", "you", "can"}
    return [word for word in query.lower().split() if word not in stopwords]

def search_pdf(query):
    keywords = extract_keywords(query)
    if not keywords:
        return None
    try:
        with pdfplumber.open("medical_info.pdf") as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text:
                    continue
                for sentence in re.split(r'(?<=[.!?])\s+', text):
                    if any(word in sentence.lower() for word in keywords):
                        return f"I found information: {sentence}"
    except Exception as e:
        return f"Error while reading PDF: {e}"
    return None

# ---- Get patient count for a doctor ----
def get_patient_count(doctor_name):
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM appointments WHERE doctor = %s", (doctor_name,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return result[0] if result else 0
    except Exception as e:
        return f"Error retrieving patient count: {e}"

# ---- Routes ----
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/doctors')
def doctors():
    return render_template('doctors.html')

@app.route('/appointment')
def appointment():
    return render_template('appointment.html')

# Web form appointment route
@app.route('/book', methods=['POST'])
def book():
    name = request.form.get('name')
    doctor = request.form.get('doctor')
    date_ = request.form.get('date')
    time = request.form.get('time')
    notes = request.form.get('notes')

    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO appointments (name, doctor, date, time, notes)
            VALUES (%s, %s, %s, %s, %s)
        """, (name, doctor, date_, time, notes))
        conn.commit()
        cursor.close()
        conn.close()
        return "<h2>Appointment booked successfully!</h2><a href='/'>Back to Home</a>"
    except Exception as e:
        return f"<h2>Failed to book appointment:</h2> {str(e)}"

# ✅ Chatbot booking route (called by JavaScript)
@app.route('/book_appointment', methods=['POST'])
def book_appointment():
    data = request.get_json()
    name = data.get('name')
    phone = data.get('phone')
    doctor = data.get('doctor')
    date_ = data.get('date')

    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO appointments (name, phone, doctor, date)
            VALUES (%s, %s, %s, %s)
        """, (name, phone, doctor, date_))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": "✅ Appointment booked successfully!"})
    except Exception as e:
        return jsonify({"message": f"❌ Failed to book appointment: {str(e)}"}), 500

# Chatbot endpoint
# ... [imports and previous code remain unchanged above]

@app.route('/chat', methods=['POST'])
def chat():
    user_message = request.json.get('message').strip().lower()
    response = ""
    user_data = load_user_data()

    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)

        # Basic greetings
        if user_message in ["hi", "hello","hey"]:
            response = "Hello! How can I assist you at HealthyCare Hospital?"

        elif user_message in ["bye", "goodbye"]:
            response = "Goodbye! Stay healthy!"

        # Today's appointments
        elif "today's appointments" in user_message or "appointments today" in user_message:
            today = date.today().isoformat()
            cursor.execute("SELECT * FROM appointments WHERE date = %s", (today,))
            results = cursor.fetchall()
            if results:
                response = "📅 Today's Appointments:\n"
                for row in results:
                    response += f"- {row['name']} with {row['doctor']} at {row.get('time', 'N/A')}\n"
            else:
                response = "There are no appointments scheduled for today."

        # Doctor's patient count
        elif "how many patients" in user_message:
            match = re.search(r"dr\.?\s+([a-z\s]+)", user_message)
            if match:
                doctor_name = "Dr. " + match.group(1).title().strip()
                cursor.execute("SELECT COUNT(*) as count FROM appointments WHERE doctor LIKE %s", (f"%{doctor_name}%",))
                count = cursor.fetchone()["count"]
                response = f"{doctor_name} has {count} patient(s) with appointments."
            else:
                response = "Please specify the doctor's name."

        # Patient-specific appointments
        elif "appointment for" in user_message or "patient" in user_message:
            match = re.search(r"(appointment|patient)\s+(for\s+)?([a-z\s]+)", user_message)
            if match:
                patient_name = match.group(3).title().strip()
                cursor.execute("SELECT * FROM appointments WHERE name = %s", (patient_name,))
                results = cursor.fetchall()
                if results:
                    response = f"🧾 Appointment(s) for {patient_name}:\n"
                    for row in results:
                        response += f"- {row['doctor']} on {row['date']} at {row.get('time', 'N/A')}\n"
                else:
                    response = f"No appointments found for {patient_name}."
            else:
                response = "Please specify the patient's name."

        else:
            # Learn and store name
            name_match = re.match(r"my name is ([a-z\s]+)", user_message, re.IGNORECASE)
            if name_match:
                name = name_match.group(1).title().strip()
                user_data["name"] = name
                save_user_data(user_data)
                response = f"Got it! I’ll remember your name is {name}."
                return jsonify({"reply": response})  # <-- Important!

            elif "what is my name" in user_message and "name" in user_data:
                response = f"Your name is {user_data['name']}."
                return jsonify({"reply": response})  # <-- Important!

            # Learn and store favorite doctor
            doctor_match = re.match(r"my favorite doctor is ([a-z\s.]+)", user_message)
            if doctor_match:
                fav_doc = doctor_match.group(1).title().strip()
                user_data["favorite_doctor"] = fav_doc
                save_user_data(user_data)
                response = f"Okay, I’ll remember that your favorite doctor is {fav_doc}."
                return jsonify({"reply": response})  # <-- Important!

            elif "who is my favorite doctor" in user_message and "favorite_doctor" in user_data:
                response = f"Your favorite doctor is {user_data['favorite_doctor']}."

            elif any(phrase in user_message for phrase in ["book an appointment", "make an appointment", "appointment booking"]):
                response = "🗓️ Sure! You can book an appointment [here](/appointment) or tell me your name, doctor, date, and time."

            else:
                # Fallback to PDF or doctor info
                disease_info = search_pdf(user_message)
                doctor_info = search_doctor_info(user_message)
                if disease_info and doctor_info:
                    response = f"📚 Disease Info:\n{disease_info}\n\n👨‍⚕️ Recommended Doctor:\n{doctor_info}"
                elif disease_info:
                    response = f"📚 Disease Info:\n{disease_info}"
                elif doctor_info:
                    response = f"👨‍⚕️ Recommended Doctor:\n{doctor_info}"
                else:
                    response = "Sorry, I couldn't find relevant information."

        cursor.close()
        conn.close()

    except Exception as e:
        response = f"Error processing your request: {str(e)}"

    return jsonify({"reply": response})

if __name__ == "__main__":
    app.run(debug=True)
