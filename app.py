# ===============================
# 1. IMPORT LIBRARY
# ===============================
from flask import Flask, render_template, request, redirect, session
import mysql.connector
import joblib
from fuzzywuzzy import fuzz

# ===============================
# 2. BUAT APLIKASI FLASK
# ===============================
app = Flask(__name__)
app.secret_key = "secret123"

# ===============================
# 3. KONEKSI DATABASE
# ===============================
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="sistem_pakar1"
)

# ===============================
# 4. LOAD MODEL MACHINE LEARNING
# ===============================
model = joblib.load("model1(1).pkl")
mlb = joblib.load("mlb1(1).pkl")
le = joblib.load("label1.pkl")

# ===============================
# 5. LOGIN
# ===============================
@app.route("/", methods=["GET","POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        with db.cursor(dictionary=True, buffered=True) as cursor:
            cursor.execute(
                "SELECT * FROM users WHERE username=%s AND password=%s",
                (username, password)
            )
            user = cursor.fetchone()
        if user:
            session["user_id"] = int(user["id"])
            session["role"] = user["role"]
            return redirect("/admin" if user["role"]=="admin" else "/index")
        else:
            error = "Username atau password salah"
    return render_template("login.html", error=error)

# ===============================
# 6. REGISTER
# ===============================
@app.route("/register", methods=["GET","POST"])
def register():
    if request.method=="POST":
        username = request.form.get("username")
        password = request.form.get("password")
        with db.cursor() as cursor:
            cursor.execute(
                "INSERT INTO users (username,password,role) VALUES (%s,%s,%s)",
                (username, password, "user")
            )
            db.commit()
        return redirect("/")
    return render_template("register.html")

# ===============================
# 7. LANDING PAGE USER
# ===============================
@app.route("/index")
def index():
    if "user_id" not in session:
        return redirect("/")
    return render_template("index.html")

# ===============================
# 8. HALAMAN USER / DIAGNOSA
# ===============================
@app.route("/user", methods=["GET","POST"])
def user():
    if "user_id" not in session:
        return redirect("/")
    user_id = int(session["user_id"])

    # Ambil data user
    with db.cursor(dictionary=True, buffered=True) as cursor:
        cursor.execute("SELECT username FROM users WHERE id=%s", (user_id,))
        user_data = cursor.fetchone()

    # ✅ FIX: jangan pakai None
    hasil = ""
    penanganan = ""
    gejala = ""

    if request.method == "POST":
        gejala = request.form.get("gejala")
        text_lower = gejala.lower() if gejala else ""

        # Fuzzy matching
        gejala_user = [g for g in mlb.classes_ if fuzz.token_set_ratio(g.lower(), text_lower) > 80]

        if not gejala_user:
            hasil = "Gejala tidak dikenali"
            penanganan = "-"
        else:
            input_vector = mlb.transform([gejala_user])
            pred = model.predict(input_vector)
            penyakit = le.inverse_transform(pred)[0]

            with db.cursor(dictionary=True, buffered=True) as cursor:
                cursor.execute("SELECT penanganan FROM penyakit WHERE nama_penyakit=%s", (penyakit,))
                data = cursor.fetchone()
                penanganan = data["penanganan"] if data else "-"
                hasil = penyakit

        # Simpan riwayat
        with db.cursor() as cursor:
            cursor.execute(
                "INSERT INTO diagnosa (user_id, gejala, penyakit, penanganan, tgl) VALUES (%s,%s,%s,%s,NOW())",
                (user_id, gejala or "-", hasil or "-", penanganan or "-")
            )
            db.commit()

    # Ambil riwayat
    with db.cursor(dictionary=True, buffered=True) as cursor:
        cursor.execute(
            "SELECT id, gejala, penyakit, penanganan, tgl, saran_dokter "
            "FROM diagnosa WHERE user_id=%s ORDER BY tgl DESC",
            (user_id,)
        )
        riwayat = cursor.fetchall()

    return render_template(
        "user.html",
        user_data=user_data,
        riwayat=riwayat,
        hasil=hasil,
        penanganan=penanganan,
        gejala=gejala
    )

# ===============================
# 9. HALAMAN ADMIN
# ===============================
@app.route("/admin")
def admin():
    if "user_id" not in session or session.get("role") != "admin":
        return redirect("/")
    with db.cursor(dictionary=True, buffered=True) as cursor:
        cursor.execute("SELECT * FROM penyakit")
        data = cursor.fetchall()
        cursor.execute("""
            SELECT diagnosa.id, users.username, diagnosa.gejala, diagnosa.penyakit,
                   diagnosa.penanganan, diagnosa.tgl, diagnosa.saran_dokter
            FROM diagnosa
            JOIN users ON diagnosa.user_id = users.id
            ORDER BY diagnosa.tgl DESC
        """)
        riwayat_all = cursor.fetchall()
    return render_template("admin.html", data=data, riwayat_all=riwayat_all)

# ===============================
# 10. TAMBAH SARAN
# ===============================
@app.route("/tambah_saran/<int:id>", methods=["GET","POST"])
def tambah_saran(id):
    if "user_id" not in session or session.get("role") != "admin":
        return redirect("/")
    with db.cursor(dictionary=True, buffered=True) as cursor:
        cursor.execute("""
            SELECT diagnosa.id, users.username, diagnosa.gejala, diagnosa.penyakit,
                   diagnosa.penanganan, diagnosa.tgl, diagnosa.saran_dokter
            FROM diagnosa
            JOIN users ON diagnosa.user_id = users.id
            WHERE diagnosa.id=%s
        """, (id,))
        data = cursor.fetchone()
    if request.method=="POST":
        saran = request.form.get("saran_dokter")
        with db.cursor() as cursor:
            cursor.execute("UPDATE diagnosa SET saran_dokter=%s WHERE id=%s", (saran, id))
            db.commit()
        return redirect("/admin")
    return render_template("tambah_saran.html", data=data)

# ===============================
# 11. DELETE
# ===============================
@app.route("/delete/<int:id>")
def delete_riwayat(id):
    if "user_id" not in session:
        return redirect("/")
    with db.cursor(dictionary=True, buffered=True) as cursor:
        cursor.execute("SELECT user_id FROM diagnosa WHERE id=%s", (id,))
        data = cursor.fetchone()
        if not data: return redirect("/user")
        if session.get("role")!="admin" and data["user_id"]!=session["user_id"]:
            return redirect("/user")
    with db.cursor() as cursor:
        cursor.execute("DELETE FROM diagnosa WHERE id=%s", (id,))
        db.commit()
    return redirect("/admin" if session.get("role")=="admin" else "/user")

# ===============================
# 12. LOGOUT
# ===============================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ===============================
# 13. RUN
# ===============================
if __name__ == "__main__":
    app.run(debug=True)