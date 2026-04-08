from flask import Flask, render_template, request, redirect, session
import sqlite3

print("Starting app.py...")

app = Flask(__name__)
app.secret_key = "dev_key"


def db():
    con = sqlite3.connect("app.db")
    con.row_factory = sqlite3.Row
    return con


@app.route("/")
def home():                                                                    
    return redirect("/dashboard")

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    con = db()
    groups = con.execute("SELECT * FROM study_groups").fetchall()

    group_data = []

    for g in groups:
        members = con.execute("""
            SELECT users.email
            FROM group_members
            JOIN users ON group_members.user_id = users.id
            WHERE group_members.group_id = ?
        """, (g["id"],)).fetchall()

        group_data.append({
            "id": g["id"],
            "course_code": g["course_code"],
            "current_size": g["current_size"],
            "capacity": g["capacity"],
            "members": [m["email"] for m in members],
            "joined": session["email"] in [m["email"] for m in members]
        })

    con.close()

    return render_template(
        "dashboard.html",
        groups=group_data,
        email=session["email"],
        role=session["role"]
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()

        if not email.endswith("@mylaurier.ca"):
            return render_template("login.html", error="Only Laurier students allowed.")

        con = db()
        user = con.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        if not user:
            con.execute(
                "INSERT INTO users (email, role) VALUES (?, ?)",
                (email, "student")
            )
            con.commit()
            user = con.execute(
                "SELECT * FROM users WHERE email = ?",
                (email,)
            ).fetchone()

        con.close()

        session["user_id"] = user["id"]
        session["email"] = user["email"]
        session["role"] = user["role"]

        return redirect("/dashboard")

    return render_template("login.html", error=None)


@app.route("/groups/create", methods=["GET", "POST"])
def create_group():
    if "user_id" not in session:
        return redirect("/login")

    if request.method == "POST":
        course_code = request.form["course_code"].strip().upper()
        capacity = int(request.form["capacity"])

        con = db()
        con.execute("""
            INSERT INTO study_groups (course_code, creator_user_id, capacity, current_size)
            VALUES (?, ?, ?, 0)
        """, (course_code, session["user_id"], capacity))
        con.commit()
        con.close()

        return redirect("/dashboard")

    return render_template("create_group.html")


@app.route("/groups/<int:group_id>/join", methods=["POST"])
def join_group(group_id):
    if "user_id" not in session:
        return redirect("/login")

    con = db()

    user = con.execute(
        "SELECT role FROM users WHERE id = ?",
        (session["user_id"],)
    ).fetchone()

    group = con.execute(
        "SELECT capacity, current_size FROM study_groups WHERE id = ?",
        (group_id,)
    ).fetchone()

    if not group:
        con.close()
        return "Group not found.", 404

    if group["current_size"] >= group["capacity"]:
        con.close()
        return "Group is full.", 400

    try:
        con.execute(
            "INSERT INTO group_members (group_id, user_id) VALUES (?, ?)",
            (group_id, session["user_id"])
        )
        con.execute(
            "UPDATE study_groups SET current_size = current_size + 1 WHERE id = ?",
            (group_id,)
        )
        con.commit()
    except sqlite3.IntegrityError:
        con.close()
        return "You are already in this group.", 400

    con.close()
    return redirect("/dashboard")


@app.route("/mentor/check", methods=["GET", "POST"])
def mentor_check():
    if "user_id" not in session:
        return redirect("/login")

    result = None
    eligible = False

    if request.method == "POST":
        course_code = request.form["course_code"].strip().upper()

        passed_courses = ["CP317", "CP312"]

        if course_code in passed_courses:
            result = f"Eligible to mentor {course_code}"
            eligible = True
        else:
            result = f"Not eligible to mentor {course_code}"

    return render_template("mentor_check.html", result=result, eligible=eligible)



@app.route("/mentor/apply", methods=["POST"])
def mentor_apply():
    if "user_id" not in session:
        return redirect("/login")

    con = db()

    con.execute(
        "UPDATE users SET role = 'mentor' WHERE id = ?",
        (session["user_id"],)
    )
    con.commit()

    updated_user = con.execute(
        "SELECT * FROM users WHERE id = ?",
        (session["user_id"],)
    ).fetchone()

    con.close()

    session["role"] = updated_user["role"]

    return redirect("/dashboard")

@app.route("/group/<int:group_id>/chat")
def chat(group_id):
    if "user_id" not in session:
        return redirect("/login")
    con=db()
    messages = con.execute("""
        SELECT messages.message_text, users.email
        FROM messages
        JOIN users ON messages.user_id = users.id
        WHERE messages.group_id = ?
        ORDER BY messages.timestamp ASC
    """, (group_id,)).fetchall()
    return render_template("chat.html", messages=messages, group_id=group_id)

@app.route("/send_message", methods=["POST"])
def send_message():
    if "user_id" not in session:
        return redirect("/login")

    group_id = request.form["group_id"]
    message = request.form["message"]

    con = db()
    con.execute("""
        INSERT INTO messages (group_id, user_id, message_text)
        VALUES (?, ?, ?)
    """, (group_id, session["user_id"], message))
    con.commit()

    return redirect(f"/group/{group_id}/chat")
@app.route("/groups/<int:group_id>/leave", methods=["POST"])
def leave_group(group_id):
    if "user_id" not in session:
        return redirect("/login")

    con = db()

    existing = con.execute(
        "SELECT * FROM group_members WHERE group_id = ? AND user_id = ?",
        (group_id, session["user_id"])
    ).fetchone()

    if not existing:
        con.close()
        return "You are not in this group.", 400

    con.execute(
        "DELETE FROM group_members WHERE group_id = ? AND user_id = ?",
        (group_id, session["user_id"])
    )

    con.execute(
        """
        UPDATE study_groups
        SET current_size = CASE
            WHEN current_size > 0 THEN current_size - 1
            ELSE 0
        END
        WHERE id = ?
        """,
        (group_id,)
    )

    con.commit()
    con.close()

    return redirect("/dashboard")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


if __name__ == "__main__":
    app.run(debug=True)
