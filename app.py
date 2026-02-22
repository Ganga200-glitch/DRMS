from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from db import get_db_connection
import os
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

# --------------------- LOGIN REQUIRED DECORATOR ---------------------
def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            if role and session.get('role') != role:
                flash("Unauthorized access")
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return wrapper
    return decorator

# --------------------- AUTH ROUTES ---------------------
@app.route('/')
def index():
    return render_template("index.html")

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])
        role = request.form['role']

        skills = request.form.get('skills')
        availability = request.form.get('availability')
        location = request.form.get('location')  # For victims

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            # Only one Admin allowed
            if role == 'Admin':
                cursor.execute("SELECT * FROM users WHERE role='Admin'")
                if cursor.fetchone():
                    flash("Admin already exists!")
                    return redirect(url_for('register'))

            # Insert into users table
            cursor.execute(
                "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                (username, password, role)
            )
            conn.commit()

            # Get the new user ID
            cursor.execute("SELECT id FROM users WHERE username=%s", (username,))
            user_id = cursor.fetchone()['id']

            if role == 'Volunteer':
                # Assign to center with fewest volunteers
                cursor.execute("""
                    SELECT id 
                    FROM reliefcenters 
                    ORDER BY (SELECT COUNT(*) FROM volunteers v WHERE v.assigned_center_id = reliefcenters.id) ASC
                    LIMIT 1
                """)
                center = cursor.fetchone()
                assigned_center_id = center['id'] if center else None

                # Insert into volunteers table
                cursor.execute(
                    "INSERT INTO volunteers (id, name, skills, availability, assigned_center_id) VALUES (%s, %s, %s, %s, %s)",
                    (user_id, username, skills, availability, assigned_center_id)
                )
                conn.commit()

            elif role == 'Victim':
                # Assign victim to the center with the fewest assigned victims
                cursor.execute("""
SELECT r.id, (SELECT COUNT(*) FROM victims v WHERE v.assigned_center_id = r.id) AS victim_count
    FROM reliefcenters r
    ORDER BY victim_count ASC, RAND()
    LIMIT 1;

""")
                center = cursor.fetchone()
                assigned_center_id = center['id'] if center else None

                # Insert into victims table with location
                cursor.execute(
                    "INSERT INTO victims (id, name, location, need_type, assigned_center_id) VALUES (%s, %s, %s, %s, %s)",
                    (user_id, username, location, None, assigned_center_id)
                )
                conn.commit()

            flash("Registration successful")
            return redirect(url_for('login'))

        except Exception as e:
            print("Error:", e)
            flash("Username already exists or DB error")
        finally:
            cursor.close()
            conn.close()

    return render_template("register.html")  


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT * FROM users WHERE username=%s AND is_active=TRUE", (username,))
            user = cursor.fetchone()
            if user and check_password_hash(user['password'], password):
                session['user_id'] = user['id']
                session['role'] = user['role']
                flash("Login successful")
                return redirect(url_for('dashboard'))
            else:
                flash("Invalid credentials or account deactivated")
        finally:
            cursor.close()
            conn.close()
    return render_template("login.html")


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --------------------- DASHBOARD ---------------------
@app.route('/dashboard')
@login_required()
def dashboard():
    return render_template("dashboard.html", role=session.get('role'))

# --------------------- RELIEF CENTERS CRUD ---------------------
@app.route('/reliefcenters')
@login_required('Admin')
def relief_centers():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM reliefcenters")
        centers = cursor.fetchall()
    except Exception as e:
        flash(f"Error fetching relief centers: {e}")
        centers = []
    finally:
        cursor.close()
        conn.close()
    return render_template("relief_centers.html", centers=centers)


@app.route('/reliefcenters/add', methods=['GET','POST'])
@login_required('Admin')
def add_reliefcenter():
    if request.method=='POST':
        name = request.form['name']
        location = request.form['location']
        capacity = request.form['capacity']
        stock = request.form['supplies_stock']
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO reliefcenters (name,location,capacity,supplies_stock) VALUES (%s,%s,%s,%s)",
                           (name,location,capacity,stock))
            conn.commit()
            flash("Relief center added")
            return redirect(url_for('relief_centers'))
        except Exception as e:
            print(e)
            flash("Error adding relief center")
        finally:
            cursor.close()
            conn.close()
    return render_template("add_relief_center.html")

@app.route('/reliefcenters/edit/<int:center_id>', methods=['GET','POST'])
@login_required('Admin')
def edit_reliefcenter(center_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        if request.method=='POST':
            name = request.form['name']
            location = request.form['location']
            capacity = request.form['capacity']
            stock = request.form['supplies_stock']
            cursor.execute("UPDATE reliefcenters SET name=%s,location=%s,capacity=%s,supplies_stock=%s WHERE id=%s",
                           (name,location,capacity,stock,center_id))
            conn.commit()
            flash("Relief center updated")
            return redirect(url_for('relief_centers'))
        cursor.execute("SELECT * FROM reliefcenters WHERE id=%s", (center_id,))
        center = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()
    return render_template("edit_relief_center.html", center=center)

@app.route('/reliefcenters/delete', methods=['POST'])
@login_required('Admin')
def delete_reliefcenter():
    data = request.get_json()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM reliefcenters WHERE id=%s", (data['id'],))
        conn.commit()
        return jsonify({"status":"success"})
    except Exception as e:
        print(e)
        return jsonify({"status":"error"})
    finally:
        cursor.close()
        conn.close()

# --------------------- VOLUNTEERS CRUD ---------------------
# ---------------- Volunteers List ----------------
@app.route('/volunteers')
@login_required('Admin')
def volunteers():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT v.id, v.name, v.skills, v.availability, v.assigned_center_id, r.name AS center_name
        FROM volunteers v
        LEFT JOIN reliefcenters r ON v.assigned_center_id = r.id
    """)
    volunteers = cursor.fetchall()
    cursor.execute("SELECT id, name FROM reliefcenters")
    centers = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("volunteers.html", volunteers=volunteers, centers=centers)


# ---------------- Add Volunteer ----------------
@app.route('/volunteers/add', methods=['GET', 'POST'])
@login_required('Admin')
def add_volunteer():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name FROM reliefcenters")
    centers = cursor.fetchall()

    if request.method == 'POST':
        name = request.form.get('name')
        skills = request.form.get('skills')
        availability = request.form.get('availability')
        assigned_center_id = request.form.get('assigned_center_id') or None

        if not name or not skills or not availability:
            flash("Please fill all required fields.", "danger")
            return render_template("add_volunteer.html", volunteer=None, centers=centers)

        try:
            # 1️⃣ Insert into users first
            cursor.execute(
                "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
                (name, generate_password_hash("default123"), "Volunteer")
            )
            conn.commit()

            # 2️⃣ Get the newly created user ID
            cursor.execute("SELECT id FROM users WHERE username=%s", (name,))
            user_id = cursor.fetchone()['id']

            # 3️⃣ Insert into volunteers using the same ID
            cursor.execute(
                "INSERT INTO volunteers (id, name, skills, availability, assigned_center_id) VALUES (%s, %s, %s, %s, %s)",
                (user_id, name, skills, availability, assigned_center_id)
            )
            conn.commit()
            flash("Volunteer added successfully!", "success")
            return redirect(url_for('volunteers'))

        except Exception as e:
            print("Error adding volunteer:", e)
            flash("Error adding volunteer. Please try again.", "danger")
        finally:
            cursor.close()
            conn.close()

    cursor.close()
    conn.close()
    return render_template("add_volunteer.html", volunteer=None, centers=centers)


# ---------------- Edit Volunteer ----------------
@app.route('/volunteers/edit/<int:volunteer_id>', methods=['GET', 'POST'])
@login_required('Admin')
def edit_volunteer(volunteer_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM volunteers WHERE id=%s", (volunteer_id,))
    volunteer = cursor.fetchone()
    cursor.execute("SELECT id, name FROM reliefcenters")
    centers = cursor.fetchall()

    if not volunteer:
        flash("Volunteer not found.", "danger")
        return redirect(url_for('volunteers'))

    if request.method == 'POST':
        name = request.form.get('name')
        skills = request.form.get('skills')
        availability = request.form.get('availability')
        assigned_center_id = request.form.get('assigned_center_id') or None

        if not name or not skills or not availability:
            flash("Please fill all required fields.", "danger")
            return render_template("add_volunteer.html", volunteer=volunteer, centers=centers)

        try:
            # 1️⃣ Update users table username
            cursor.execute(
                "UPDATE users SET username=%s WHERE id=%s",
                (name, volunteer_id)
            )
            # 2️⃣ Update volunteers table
            cursor.execute(
                "UPDATE volunteers SET name=%s, skills=%s, availability=%s, assigned_center_id=%s WHERE id=%s",
                (name, skills, availability, assigned_center_id, volunteer_id)
            )
            conn.commit()
            flash("Volunteer updated successfully!", "success")
            return redirect(url_for('volunteers'))
        except Exception as e:
            print("Error updating volunteer:", e)
            flash("Error updating volunteer. Please try again.", "danger")

    cursor.close()
    conn.close()
    return render_template("add_volunteer.html", volunteer=volunteer, centers=centers)

# ---------------- Delete Volunteer ----------------
@app.route('/volunteers/delete', methods=['POST'])
@login_required('Admin')
def delete_volunteer():
    data = request.get_json()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM volunteers WHERE id=%s", (data['id'],))
        cursor.execute("DELETE FROM users WHERE id=%s", (data['id'],))
        conn.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        print("Error deleting volunteer:", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        cursor.close()
        conn.close()

# --------------------- VICTIMS CRUD ---------------------
@app.route('/victims')
@login_required('Admin')
def victims():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""SELECT v.*, r.name as center_name 
                          FROM victims v LEFT JOIN reliefcenters r 
                          ON v.assigned_center_id=r.id""")
        victims = cursor.fetchall()
        cursor.execute("SELECT * FROM reliefcenters")
        centers = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()
    return render_template("victims.html", victims=victims, centers=centers)

@app.route('/victims/add', methods=['GET','POST'])
@login_required('Admin')
def add_victim():
    if request.method == 'POST':
        username = request.form['name']
        name = request.form['name']
        location = request.form['location']
        need_type = request.form['need_type']
        assigned_center_id = request.form.get('assigned_center_id') or None

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            # Insert into users table
            cursor.execute("""
                INSERT INTO users (username, password, role)
                VALUES (%s, %s, %s)
            """, (username, generate_password_hash("default123"), "Victim"))
            user_id = cursor.lastrowid

            # Insert into victims table
            cursor.execute("""
                INSERT INTO victims (id, name, location, need_type, assigned_center_id)
                VALUES (%s, %s, %s, %s, %s)
            """, (user_id, name, location, need_type, assigned_center_id))

            conn.commit()
            flash("Victim added successfully")
            return redirect(url_for('victims'))
        except Exception as e:
            print("Error adding victim:", e)
            flash("Error adding victim. Please try again.")
        finally:
            cursor.close()
            conn.close()

    # GET request: show form
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM reliefcenters")
    centers = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("add_victim.html", centers=centers)



@app.route('/victims/edit/<int:victim_id>', methods=['GET','POST'])
@login_required('Admin')
def edit_victim(victim_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        if request.method=='POST':
            name = request.form['name']
            location = request.form['location']
            need_type = request.form['need_type']
            assigned_center_id = request.form['assigned_center_id']
            cursor.execute("UPDATE victims SET name=%s,location=%s,need_type=%s,assigned_center_id=%s WHERE id=%s",
                           (name,location,need_type,assigned_center_id,victim_id))
            conn.commit()
            flash("Victim updated")
            return redirect(url_for('victims'))
        cursor.execute("SELECT * FROM victims WHERE id=%s", (victim_id,))
        victim = cursor.fetchone()
        cursor.execute("SELECT * FROM reliefcenters")
        centers = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()
    return render_template("edit_victim.html", victim=victim, centers=centers)
@app.route('/victims/delete', methods=['POST'])
@login_required('Admin')
def delete_victim():
    data = request.get_json()
    victim_id = data.get('id')

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # First delete from victims table
        cursor.execute("DELETE FROM victims WHERE id=%s", (victim_id,))
        # Then delete from users table if linked
        cursor.execute("DELETE FROM users WHERE id=%s", (victim_id,))
        conn.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        print("Error deleting victim:", e)
        return jsonify({"status": "error", "message": str(e)})
    finally:
        cursor.close()
        conn.close()




# --------------------- SUPPLIES CRUD ---------------------
@app.route('/supplies')
@login_required('Admin')
def supplies():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""SELECT s.*, r.name as center_name 
                          FROM supplies s LEFT JOIN reliefcenters r 
                          ON s.center_id=r.id""")
        supplies = cursor.fetchall()
        cursor.execute("SELECT * FROM reliefcenters")
        centers = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()
    return render_template("supplies.html", supplies=supplies, centers=centers)

@app.route('/supplies/add', methods=['GET','POST'])
@login_required('Admin')
def add_supply():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM reliefcenters")
        centers = cursor.fetchall()
        if request.method=='POST':
            item_name = request.form['item_name']
            quantity = request.form['quantity']
            center_id = request.form['center_id']
            cursor.execute("INSERT INTO supplies (item_name,quantity,center_id) VALUES (%s,%s,%s)",
                           (item_name,quantity,center_id))
            conn.commit()
            flash("Supply added")
            return redirect(url_for('supplies'))
    finally:
        cursor.close()
        conn.close()
    return render_template("add_supply.html", centers=centers)

@app.route('/supplies/edit/<int:supply_id>', methods=['GET','POST'])
@login_required('Admin')
def edit_supply(supply_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        if request.method=='POST':
            item_name = request.form['item_name']
            quantity = request.form['quantity']
            center_id = request.form['center_id']
            cursor.execute("UPDATE supplies SET item_name=%s,quantity=%s,center_id=%s WHERE id=%s",
                           (item_name,quantity,center_id,supply_id))
            conn.commit()
            flash("Supply updated")
            return redirect(url_for('supplies'))
        cursor.execute("SELECT * FROM supplies WHERE id=%s", (supply_id,))
        supply = cursor.fetchone()
        cursor.execute("SELECT * FROM reliefcenters")
        centers = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()
    return render_template("edit_supply.html", supply=supply, centers=centers)

@app.route('/supplies/delete', methods=['POST'])
@login_required('Admin')
def delete_supply():
    data = request.get_json()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM supplies WHERE id=%s", (data['id'],))
        conn.commit()
        return jsonify({"status":"success"})
    except:
        return jsonify({"status":"error"})
    finally:
        cursor.close()
        conn.close()

# --------------------- DONOR ROUTES ---------------------
@app.route('/donate', methods=['GET','POST'])
@login_required('Donor')
def donate():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM reliefcenters")
        centers = cursor.fetchall()
        if request.method=='POST':
            donor_name = request.form['donor_name']
            type_ = request.form['type']
            amount = request.form.get('amount') or None
            item_name = request.form.get('item_name') or None
            quantity = request.form.get('quantity') or None
            center_id = request.form.get('center_id') or None
            cursor.execute("INSERT INTO donations (donor_name,type,amount,item_name,quantity,center_id) VALUES (%s,%s,%s,%s,%s,%s)",
                           (donor_name,type_,amount,item_name,quantity,center_id))
            conn.commit()
            flash("Donation successful")
            return redirect(url_for('donations'))
    finally:
        cursor.close()
        conn.close()
    return render_template("donate.html", centers=centers)

@app.route('/donations')
@login_required('Donor')
def donations():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""SELECT d.*, r.name as center_name 
                          FROM donations d LEFT JOIN reliefcenters r 
                          ON d.center_id=r.id""")
        donations = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()
    return render_template("donations.html", donations=donations)

# --------------------- ALERTS ---------------------
@app.route('/alerts')
@login_required('Admin')
def alerts():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id, CONCAT('Low stock for ', item_name) AS message, center_name FROM LowSuppliesView")
        alerts = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()
    return render_template("alerts.html", alerts=alerts)


# --------------------- REPORTS ---------------------
@app.route('/reports/low_supplies')
@login_required('Admin')
def low_supplies_report():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM LowSuppliesView")
        low_supplies = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()
    return render_template("low_supplies_report.html", low_supplies=low_supplies)

@app.route('/reports/top_volunteers')
@login_required('Admin')
def top_volunteers_report():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
    SELECT v.id, v.name, v.skills, r.name as center_name,
           COUNT(t.id) AS tasks_completed
    FROM volunteers v
    LEFT JOIN reliefcenters r ON v.assigned_center_id = r.id
    LEFT JOIN volunteer_tasks t 
           ON v.id = t.volunteer_id AND t.date_completed IS NOT NULL
    GROUP BY v.id
    HAVING tasks_completed >= 3  -- or 3 depending on your threshold
""")

        top_volunteers = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()
    return render_template("top_volunteers_report.html", top_volunteers=top_volunteers)

# --------------------- VOLUNTEER DASHBOARD ---------------------
@app.route('/volunteer/dashboard')
@login_required('Volunteer')
def volunteer_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Assigned center info
    cursor.execute("""
        SELECT r.name, r.location
        FROM reliefcenters r
        JOIN volunteers v ON v.assigned_center_id = r.id
        WHERE v.id = %s
    """, (session['user_id'],))
    center = cursor.fetchone()
    
    # Task summary
    cursor.execute("""
        SELECT 
            COUNT(*) AS total,
            SUM(date_completed IS NOT NULL) AS completed,
            SUM(date_completed IS NULL) AS pending
        FROM volunteer_tasks
        WHERE volunteer_id = %s
    """, (session['user_id'],))
    task_summary = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    return render_template(
        "volunteer_dashboard.html",
        center=center,
        task_summary=task_summary
    )


# --------------------- VOLUNTEER TASKS PAGE ---------------------
@app.route('/volunteer/tasks')
@login_required('Volunteer')
def volunteer_tasks():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT t.*, v.name as victim_name
        FROM volunteer_tasks t
        LEFT JOIN victims v ON t.victim_id = v.id
        WHERE t.volunteer_id = %s
        ORDER BY t.date_assigned DESC
    """, (session['user_id'],))
    tasks = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template("volunteer_tasks.html", tasks=tasks)


# --------------------- UPDATE TASK STATUS ---------------------
@app.route('/volunteer/task/update/<int:task_id>', methods=['POST'])
@login_required('Volunteer')
def update_task(task_id):
    status = request.form['status']
    conn = get_db_connection()
    cursor = conn.cursor()
    if status == 'completed':
        cursor.execute("UPDATE volunteer_tasks SET date_completed=NOW() WHERE id=%s", (task_id,))
        conn.commit()
    cursor.close()
    conn.close()
    flash("Task updated successfully!")
    return redirect(url_for('volunteer_tasks'))

# --------------------- DONOR DASHBOARD ---------------------
@app.route('/donor/dashboard')
@login_required('Donor')
def donor_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Donation history
    cursor.execute("""
        SELECT d.*, r.name as center_name
        FROM donations d
        LEFT JOIN reliefcenters r ON d.center_id = r.id
        WHERE d.donor_name = (SELECT username FROM users WHERE id=%s)
    """, (session['user_id'],))
    donations = cursor.fetchall()
    
    # Impact report (number of victims helped)
    cursor.execute("""
        SELECT SUM(vt.id IS NOT NULL) as victims_helped
        FROM donations d
        LEFT JOIN volunteer_tasks vt ON vt.task_description LIKE CONCAT('%', d.item_name, '%')
        WHERE d.donor_name = (SELECT username FROM users WHERE id=%s)
    """, (session['user_id'],))
    impact = cursor.fetchone()
    
    cursor.close()
    conn.close()
    return render_template("donor_dashboard.html", donations=donations, impact=impact)
# --------------------- VICTIM DASHBOARD ---------------------
@app.route('/victim/request/add', methods=['GET', 'POST'])
@login_required('Victim')
def add_request():
    if request.method == 'POST':
        need_type = request.form['need_type']
        location = request.form['location']

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Insert new request into requests table
        cursor.execute("""
            INSERT INTO requests (victim_id, need_type, location)
            VALUES (%s, %s, %s)
        """, (session['user_id'], need_type, location))
        conn.commit()

        cursor.close()
        conn.close()

        flash("Request submitted successfully!")
        return redirect(url_for('victim_dashboard'))

    return render_template("add_request.html")


@app.route('/victim_dashboard')
@login_required(role='Victim')
def victim_dashboard():
    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Get victim info
        cursor.execute("SELECT name, assigned_center_id FROM victims WHERE id=%s", (user_id,))
        victim = cursor.fetchone()
        
        # Get assigned center name
        center_name = None
        if victim and victim['assigned_center_id']:
            cursor.execute("SELECT name FROM reliefcenters WHERE id=%s", (victim['assigned_center_id'],))
            center = cursor.fetchone()
            if center:
                center_name = center['name']
        
        # Get victim requests
        cursor.execute("""
            SELECT need_type, location, status, created_at
            FROM requests
            WHERE victim_id=%s
            ORDER BY created_at DESC
        """, (user_id,))
        requests = cursor.fetchall()
        
    finally:
        cursor.close()
        conn.close()
    
    return render_template("victim_dashboard.html",
                           victim_name=victim['name'] if victim else "Victim",
                           assigned_center=center_name,
                           requests=requests)




@app.route('/admin/donations')
@login_required('Admin')
def admin_donations():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT d.*, r.name as center_name
            FROM donations d
            LEFT JOIN reliefcenters r ON d.center_id=r.id
        """)
        donations = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()
    return render_template("admin_donations.html", donations=donations)


# --------------------- ADMIN ASSIGN TASK ---------------------

@app.route('/admin/assign_task', methods=['GET', 'POST'])
@login_required('Admin')
def assign_task():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Get volunteers and victims for dropdowns
    cursor.execute("SELECT id, name FROM volunteers")
    volunteers = cursor.fetchall()
    cursor.execute("SELECT id, name FROM victims")
    victims = cursor.fetchall()

    if request.method == 'POST':
        volunteer_id = request.form['volunteer_id']
        victim_id = request.form.get('victim_id') or None
        task_description = request.form['task_description']

        cursor.execute("""
            INSERT INTO volunteer_tasks (volunteer_id, victim_id, task_description, date_assigned)
            VALUES (%s, %s, %s, NOW())
        """, (volunteer_id, victim_id, task_description))
        conn.commit()
        flash("Task assigned successfully!")
        return redirect(url_for('assign_task'))

    cursor.close()
    conn.close()
    return render_template("assign_task.html", volunteers=volunteers, victims=victims)

# --------------------- ADMIN VIEW ALL TASKS ---------------------
@app.route('/admin/tasks')
@login_required('Admin')
def admin_tasks():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT t.*, 
                   v.name as volunteer_name, 
                   vc.name as victim_name,
                   CASE WHEN t.date_completed IS NULL THEN 'Pending' ELSE 'Completed' END as status
            FROM volunteer_tasks t
            LEFT JOIN volunteers v ON t.volunteer_id = v.id
            LEFT JOIN victims vc ON t.victim_id = vc.id
            ORDER BY t.date_assigned DESC
        """)
        tasks = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()
    return render_template("admin_tasks.html", tasks=tasks)
@app.route('/victim/requests')
@login_required('Victim')
def view_requests():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT id, need_type, location, status, created_at
        FROM requests
        WHERE victim_id=%s
        ORDER BY created_at DESC
    """, (session['user_id'],))
    requests = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template('victim_requests.html', requests=requests)
@app.route('/admin_requests')
@login_required(role='Admin')
def admin_requests():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT r.id, v.name AS victim_name, r.need_type, r.location, r.status, r.created_at
            FROM requests r
            JOIN victims v ON r.victim_id = v.id
            ORDER BY r.created_at DESC
        """)
        requests = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    return render_template("admin_requests.html", requests=requests)
@app.route('/update_request_status/<int:request_id>/<status>')
@login_required(role='Admin')
def update_request_status(request_id, status):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE requests SET status=%s WHERE id=%s", (status, request_id))
        conn.commit()
        flash(f"Request {request_id} updated to {status}")
    finally:
        cursor.close()
        conn.close()
    
    return redirect(url_for('admin_requests'))




# --------------------- RUN APP ---------------------
if __name__ == '__main__':
    app.run(debug=True)  