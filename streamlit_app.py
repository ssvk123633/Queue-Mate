import sqlite3
from html import escape
from pathlib import Path
import base64
import streamlit as st


def render_table(headers, rows):
    head = "".join(f"<th style='text-align:left;padding:10px;border-bottom:1px solid #dce6ee'>{escape(str(header))}</th>" for header in headers)
    body = "".join(
        "<tr>" + "".join(
            f"<td style='padding:10px;border-bottom:1px solid #eef3f7'>{escape(str(value))}</td>"
            for value in row
        ) + "</tr>"
        for row in rows
    )
    st.markdown(
        '<div style="overflow-x:auto">'
        '<table style="width:100%;border-collapse:collapse;background:white">'
        f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>",
        unsafe_allow_html=True,
    )


st.set_page_config(page_title="Smart Queue Buddy", page_icon="🏥", layout="wide")

PAGE_BACKGROUNDS = {
    "Visitor registration": "assets/registration.jpg",
    "Live queue": "assets/live_queue.jpg",
    "Host dashboard": "assets/dashboard.jpg",
}

BASE_DIR = Path(__file__).resolve().parent

def image_data_url(relative_path):
    path = BASE_DIR / relative_path
    if not path.exists():
        return ""
    image_bytes = path.read_bytes()
    return "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode()
st.markdown("""
<style>
.block-container { max-width: 1180px; }
.hero { padding: 26px 28px; border-radius: 18px; color: white;
        background: linear-gradient(135deg, rgba(15,118,110,.95), rgba(16,66,109,.92)); }
.hero h1 { margin: 0 0 6px; }
.metric-card { padding: 18px; border-radius: 14px; background: white;
               border: 1px solid #dce6ee; box-shadow: 0 8px 20px rgba(36,71,95,.08); }
[data-testid="stSidebar"] { background: rgba(255,255,255,.94); }
[data-testid="stHeader"] { background: transparent; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="hero"><h1>Smart Queue Buddy</h1><p>Public service queue registration and monitoring</p></div>', unsafe_allow_html=True)

if "visitor" not in st.session_state:
    st.session_state.visitor = None

DB_PATH = "queue.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS visitors (
        visitor_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, phone TEXT NOT NULL UNIQUE, age INTEGER,
        place TEXT, counter TEXT, verified INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS tokens (
        token_no INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
        counter TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'waiting',
        created_at TEXT NOT NULL, phone TEXT, place TEXT
    )""")

    # Add columns to databases created by an earlier version of the app.
    token_columns = {row[1] for row in conn.execute("PRAGMA table_info(tokens)").fetchall()}
    if "phone" not in token_columns:
        conn.execute("ALTER TABLE tokens ADD COLUMN phone TEXT")
    if "place" not in token_columns:
        conn.execute("ALTER TABLE tokens ADD COLUMN place TEXT")

    conn.commit()
    conn.close()

init_db()

PLACES = {
    "Hospital": ["OPD", "Emergency", "Pharmacy", "Billing"],
    "Mall": ["Customer Service", "Parking Desk", "Lost & Found"],
    "Theatre": ["Ticket Counter", "Reservation", "Refund Desk"],
    "Police Station": ["Help Desk", "Reporting", "Complaint Counter"],
    "Bank": ["Cash Counter", "Account Opening", "Loan Enquiry"],
    "Government Office": ["Enquiry", "Application", "Certificate Desk"],
    "Railway Station": ["Ticket Counter", "Reservation", "Enquiry"],
    "Bus Station": ["Booking", "Enquiry", "Luggage"],
}

page = st.sidebar.radio("Navigation", ["Visitor registration", "Live queue", "Host dashboard"])

background_url = image_data_url(PAGE_BACKGROUNDS[page])
st.markdown(f"""
<style>
.stApp {{
    background:
        linear-gradient(rgba(237,244,248,.72), rgba(223,234,242,.78)),
        url("{background_url}") center/cover fixed no-repeat;
}}
.stMainBlockContainer, .block-container {{
    background: rgba(255,255,255,.82);
    border-radius: 18px;
    padding: 20px 24px 32px;
}}
</style>
""", unsafe_allow_html=True)

if page == "Visitor registration":
    st.subheader("Visitor registration")
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("Full name")
        phone = st.text_input("Phone number", max_chars=10)
        age = st.number_input("Age", min_value=1, max_value=120, value=25)
    with col2:
        place = st.selectbox("Public place", ["Select a place", *PLACES])
        counter_name = ""
        if place != "Select a place":
            counter_name = st.selectbox("Counter / service", [f"{place} - {service}" for service in PLACES[place]])
        consent = st.checkbox("I consent to storing my information for queue verification")

    if st.button("Register and get token", type="primary", use_container_width=True):
        if not name or not phone.isdigit() or len(phone) != 10 or place == "Select a place" or not consent:
            st.error("Complete every field, use a 10-digit phone number, and accept consent.")
        else:
            from datetime import datetime
            conn = sqlite3.connect(DB_PATH)
            conn.execute("INSERT INTO visitors(name, phone, age, place, counter, verified, created_at) VALUES (?,?,?,?,?,1,?) ON CONFLICT(phone) DO UPDATE SET name=excluded.name, age=excluded.age, place=excluded.place, counter=excluded.counter, verified=1, created_at=excluded.created_at", (name, phone, age, place, counter_name, datetime.now().isoformat()))
            cur = conn.execute("INSERT INTO tokens(name, counter, status, created_at, phone, place) VALUES (?,?,?,?,?,?)", (name, counter_name, "waiting", datetime.now().isoformat(), phone, place))
            conn.commit()
            token_no = cur.lastrowid
            conn.close()
            st.session_state.visitor = {"name": name, "phone": phone, "place": place, "counter": counter_name, "token_no": token_no}
            st.success(f"Registered successfully. Your token is #{token_no} at {counter_name}.")

elif page == "Live queue":
    st.subheader("Live queue monitoring")
    place = st.selectbox("Public place", ["All places", *PLACES], key="live_place")
    from datetime import datetime
    today = datetime.now().date().isoformat()
    conn = sqlite3.connect(DB_PATH)
    query = "SELECT token_no, counter, status, created_at, place FROM tokens WHERE status='waiting' AND substr(created_at, 1, 10)=?"
    params = [today]
    if place != "All places":
        query += " AND place=?"
        params.append(place)
    query += " ORDER BY token_no"
    rows = conn.execute(query, params).fetchall()
    conn.close()

    c1, c2 = st.columns(2)
    c1.metric("Waiting visitors", len(rows))
    c2.metric("Selected place", place)
    if rows:
        headers = ["Token", "Counter", "Status", "Created", "Place"]
        render_table(headers, rows)
    else:
        st.info("No visitors are waiting for the selected place.")

else:
    st.subheader("Host dashboard")
    conn = sqlite3.connect(DB_PATH)
    visitors = conn.execute("SELECT visitor_id, name, phone, age, place, counter, verified, created_at FROM visitors ORDER BY visitor_id DESC").fetchall()
    conn.close()

    place_filter = st.selectbox("Filter by public place", ["All places", *PLACES], key="host_place")
    search = st.text_input("Search name or phone")
    filtered = [row for row in visitors if (place_filter == "All places" or row[4] == place_filter) and (not search or search.lower() in row[1].lower() or search in row[2])]

    if filtered:
        headers = ["ID", "Name", "Phone", "Age", "Place", "Counter", "Verified", "Registered"]
        display_rows = [
            (row[0], row[1], "••••••" + str(row[2])[-4:], row[3], row[4], row[5], row[6], row[7])
            for row in filtered
        ]
        render_table(headers, display_rows)
    else:
        st.info("No registered users found.")
