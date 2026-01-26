from googletrans import Translator
from dotenv import load_dotenv

from modules.mail_model import sendmailthread
load_dotenv()
from flask import Flask, request, redirect, url_for, render_template, render_template_string, flash, session, jsonify
from flask_socketio import SocketIO, emit
# import sqlite3 as sq
import os, requests, datetime, time, threading, zoneinfo, random, json
from datetime import timedelta
import sqlitecloud as sq
from functools import wraps

from modules import sendlog, sendmail, sendmailthread, del_event, detailsformat, addevent

app = Flask(__name__)
socket = SocketIO(app, cors_allowed_origins="*")
app.secret_key = os.environ.get("FLASK_SECRET")
ist = zoneinfo.ZoneInfo("Asia/Kolkata")

translations_lock = threading.Lock()

active_events = 0

def sqldb(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        db = sq.connect(os.environ.get("SQLITECLOUD"))
        db.row_factory = sq.Row
        c = db.cursor()
        final = function(c, *args, **kwargs)
        db.commit()
        db.close()
        return final
    return wrapper


@app.route("/sendsignupotp", methods=["POST", "GET"])
@sqldb
def sendotp(c):
    if request.method == "POST":
        otp = random.randint(1111,9999)
        session.permanent = True
        session["signupotp"] = otp
        email = request.form.get("email")
        checkexists = c.execute("SELECT * FROM userdetails where email=?", (email,)).fetchone()
        if checkexists:
            return "Email already exists! Please try different email."
        sendmailthread(email, "Signup OTP", f"Your signup OTP is {otp}.\nUse it to sign up in EcoCamp\n\nThankyou :)")
        return f"OTP Sent to {email}! Please check spam folder if cant find it."

@app.template_filter("datetimeformat")
def datetimeformat(value):
    return datetime.datetime.strptime(value, "%Y-%m-%d").strftime("%d %B %Y")


all_translations = {}
non_file_translations = {}

def load_translations():
        global all_translations
        try:
            with open("translations.json", "r") as f:
                all_translations = json.load(f)
                print("Translations loaded successfully.")
                sendlog(f"Translations file loaded successfully with {len(all_translations)} texts.")
        except Exception as e:
                print(f"Translation file error: {e}")
                sendlog(f"Translation file error: {e}")

def save_translations():
    global all_translations
    try:
        with open("translations.json", "w", encoding="utf-8") as f:
            json.dump(all_translations, f, indent=4, ensure_ascii=False)
            # print("Translations saved successfully.")
            # sendlog(f"Translations file saved successfuly with {len(all_translations)} texts.")
    except Exception as e:
        print(f"Error saving translation file: {e}")
        sendlog(f"Error saving translation file: {e}")

def translation_file_thread():
    global all_translations
    i = 0
    while True:
        time.sleep(60)
        with translations_lock:
            save_translations()
            with open("translations_backup.json", "w", encoding="utf-8") as f:
                json.dump(all_translations, f, indent=4, ensure_ascii=False)
            # i += 1
            # print(f"Translation file save done for {i} times.")
            # sendlog(f"Translation file save done for {i} times.")

def translate_thread(text, lang, save_file):
    global all_translations
    global non_file_translations
    try:
        t = Translator()
        translated = t.translate(text, dest=lang).text
        print(f"Translated '{text}' to '{translated}' in language '{lang}'")
    except Exception as e:
        print(f"Translation error: {e}")
        translated = text

    with translations_lock:
        translate_dict = non_file_translations if not save_file else all_translations
        existing = translate_dict.get(text, {})
        existing[lang] = translated
        translate_dict[text] = existing

@app.route("/setlanguage/<path:lang>", methods=["GET", "POST"])
def setlanguage(lang):
    if request.method == "POST":
        session.permanent = True
        session["lang"] = lang
        return "Language Set"

@app.route("/generate_ai_description", methods=["POST"])
def generate_ai_description():
    try:
        field = ["eventname", "starttime", "endtime", "eventdate", "enddate", "location", "category"]
        values = [[x,y] for x,y in request.form.items() if x in field]
        u_lang = session.get("lang", "en")

        content = f"""Generate a description based on following details in pure '{u_lang}' language all words shold be in this language only and its content also in pure '{u_lang}' language:
        Details of event is as followes: {values}
        Generate total 4x descriptions, each description should be within 500 words. Include hastags in it. And reply me in a json format as below:
        {{"desc1": "description1 in formal tone", "desc2": "description2 in informal tone", "desc3": "description3 in promotional tone", "desc4": "description4 in entertaining tone"}}
        dont include any other text other than json format in your response. dont even include any word count or anything else dont even include category name in it. Just pure description in json format."""

        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY')}",
                    "Content-Type": "application/json",
            },
            data = json.dumps({
                "model": "nvidia/nemotron-nano-9b-v2:free",
                "messages": [{"role": "user", "content": content}]
            }))
        data = response.json()
        print(data)
        output = data["choices"][0]["message"]["content"]
        to_json = json.loads(output)
    except Exception as e:
        print(f"AI Description Generation Error: {e}")
        return "Error generating description. Please try again later."
    return to_json

@app.route("/group-chat/from-event/<int:eventid>")
@sqldb
def group_chat_from_event(c, eventid):
    currentuname = session.get("username", "anonymous")
    eventdetail = c.execute("SELECT * FROM eventdetail WHERE eventid=?", (eventid,)).fetchone()
    if not eventdetail:
        return "No such event found."

    all = c.execute("SELECT * FROM messages WHERE eventid=? ORDER BY time ASC", (eventid,)).fetchall()
    try:
        username = [x["username"] for x in all]
        message = [x["message"] for x in all]
        dateti = [x["time"] for x in all]
    except:
        username, message, dateti, final = [], [], [], []
    final = zip(username, message, dateti)
    return render_template("groupchat.html", messages=final, eventid=eventid, currentuname=currentuname, eventname=eventdetail["eventname"])

@socket.on("add_grp_msg")
@sqldb
def add_group_msg(c, data):
    username = data["username"]
    message = data["message"]
    eventid = data["eventid"]
    msg_time = datetime.datetime.now(ist).strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO messages(eventid, username, message, time) VALUES(?, ?, ?, ?)", (eventid, username, message, msg_time))
    emit("new_message", {"eventid": eventid, "username": username, "message": message, "time": msg_time}, broadcast=True)

@socket.on("addeventlike")
@sqldb
def add_like(c, data):
    eventid = data["eventid"]
    byuser = data["byuser"]
    type = data["type"]
    ud = c.execute("SELECT * FROM userdetails WHERE username=?", (byuser,)).fetchone()
    if not ud["likes"]:
        liked_events = []
    else:
        liked_events = ud["likes"].split(",")
    if type == "add":
        liked_events.append(str(eventid))
    else:
        liked_events.remove(str(eventid))
    new_likes_str = ",".join(liked_events)
    c.execute("UPDATE userdetails SET likes=? WHERE username=?", (new_likes_str, byuser))
    if type == "add":
        c.execute("UPDATE eventdetail SET likes = likes + 1 WHERE eventid=?", (eventid,))
    else:
        c.execute("UPDATE eventdetail SET likes = likes - 1 WHERE eventid=?", (eventid,))
    new_likes = c.execute("SELECT likes FROM eventdetail WHERE eventid=?", (eventid,)).fetchone()["likes"]
    emit("update_like", {"eventid": eventid, "likes": new_likes}, broadcast=True)

@app.route("/user/<path:username>")
@sqldb
def user_profile(c, username):
    userfulldetails = c.execute("SELECT * FROM userdetails WHERE username=?", (username,)).fetchone()
    if not userfulldetails:
        return "User not found."
    return render_template("userprofile.html", userdetails=userfulldetails)

@app.route("/changetemplate")
def changetemplate():
        ct = session.get("template", "index.html")
        if ct == "index.html":
            session["template"] = "index2.html"
        else:
            session["template"] = "index.html"
        return "Template Changed"



@app.context_processor
def inject_globals():
    return {"translate": translate_text, "user_language": session.get("lang", "en")}


def translate_text(text, lang=None, save_file=True):
    global all_translations
    global non_file_translations
    if lang is None:
        lang = session.get("lang", "en")
    if not lang or lang == "en":
        return text
    combined_translations = {**all_translations, **non_file_translations}
    # small_keys = {k.lower(): v for k,v in combined_translations.items()}
    if not combined_translations.get(text) or not combined_translations.get(text).get(lang):
        thread = threading.Thread(target=translate_thread, args=(text, lang, save_file))
        thread.start()
    translationss = all_translations if save_file else non_file_translations
    return translationss.get(text, {}).get(lang, text)


@app.route("/")
@sqldb
def home(c):
    currentuser = session.get("name", "User")
    currentuname = session.get("username")
    print("Welcome", currentuser)
    global active_events
    active_events = active_events

    isadmin = False
    userdetails = {}
    if currentuname:
        ud = c.execute("SELECT * FROM userdetails WHERE username=?", (currentuname, )).fetchone()
        if ud and ud["role"] == "admin":
            isadmin = True
        userdetails = ud if ud else {}

    template = session.get("template", "index.html")
    return render_template(template, active_events_length=active_events, fullname=currentuser, c_user=str(currentuname).strip(), isadmin=bool(isadmin), userdetails=userdetails)


@app.route("/show_add_form")
@sqldb
def show_add_form(c):
    fv = {}
    fi = ["eventname", "email", "starttime", "endtime", "eventdate", "enddate", "location", "category", "description"]
    for x in fi:
        fv[x] = session.get(x, "")

    return render_template("addevent.html", fvalues=fv)


@app.route("/show_campaigns")
@sqldb
def show_campaigns(c):
    currentuname = session.get("username")
    c.execute("SELECT * FROM eventdetail")
    edetailslist = c.fetchall()
    alleventscat = []
    for x in edetailslist:
        cate = x["category"]
        if not cate in alleventscat:
            alleventscat.append(cate)
    allevents = {}
    for x in edetailslist:
        if x["category"] not in allevents:
            allevents[x["category"]] = []
        if x["category"] in alleventscat:
            allevents[x["category"]].append(x)

    global active_events
    total_events = [len(events) for events in allevents.values()]
    print(total_events)
    print(allevents)
    active_events = sum(total_events)

    isadmin = False
    userdetails = {}
    if currentuname:
        ud = c.execute("SELECT * FROM userdetails WHERE username=?", (currentuname, )).fetchone()
        if ud and ud["role"] == "admin":
            isadmin = True
        userdetails = ud if ud else {}

    viewuserevent = session.get("vieweventusername", f"{currentuname}")
    ve = session.get("viewyourevents", False)

    session.pop("vieweventusername", None)
    session.pop("viewyourevents", None)

    sortby = session.get("sortby", "eventdate")

    return render_template("campaigns.html", allevents=allevents, userdetails=userdetails, viewyourevents=ve, sortby=sortby,
        isadmin=bool(isadmin), c_user=str(currentuname).strip(), viewuserevent=viewuserevent)


@app.route("/viewyourevents/<path:username>", methods=["POST"])
def viewyourevents(username):
    session["viewyourevents"] = True
    session["vieweventusername"] = username
    return "OK"

@app.route("/setsortby/<path:sortby>", methods=["GET", "POST"])
def setsortby(sortby):
    if request.method == "POST":
        session["sortby"] = sortby
        return "Sort by set"

@app.route("/signup", methods=["GET", "POST"])
@sqldb
def signup(c):
    if request.method == "POST":
        username = request.form.get("username").lower()
        password = request.form.get("password")
        cpassword = request.form.get("cpassword")
        name = request.form.get("nameofuser")
        email = request.form.get("email")
        otp = request.form.get("signupotp")
        c.execute("SELECT * FROM userdetails where username=?", (username,))
        if c.fetchone():
            return "Username Already Exists"
        if c.execute("SELECT * FROM userdetails where email=?", (email,)).fetchone():
            return "Email Already Exists"
        if str(session.get("signupotp")) != str(otp).strip():
            return "Wrong Signup OTP"
        elif password != cpassword:
            return "Wrong Confirm Password"
        elif len(password) < 8:
            return "Password must be at least 8 characters long"
        else:
            c.execute("INSERT INTO userdetails(username, password, name, email) VALUES(?, ?, ?, ?)", (username, password, name, email))
            session.permanent = True
            session["username"] = username
            session["name"] = name
            session["email"] = email
            session.pop("signupotp", None)
            sendlog(f"New Signup: {name} ({username})")
            return "Signup Success ✅"

@app.route("/login", methods=["GET", "POST"])
@sqldb
def login(c):
    if request.method == "POST":
        username = request.form.get("loginusername").lower()
        password = request.form.get("loginpassword")
        c.execute("SELECT * FROM userdetails where username=? or email=?", (username, username))
        fetched = c.fetchone()
        if not fetched:
            return "No username found"
        elif password != fetched["password"]:
            return "Wrong Password"
        else:
            session.permanent = True
            session["username"] = fetched["username"]
            session["name"] = fetched["name"]
            session["email"] = fetched["email"]
            sendlog(f"User Login: {fetched['name']} ({fetched['username']})")
            return "Login Success ✅"

@app.route("/addevent", methods=["GET", "POST"])
@sqldb
def addnewevent(c):
    if request.method == "POST":
        return addevent(c, request, redirect, url_for)


@app.route("/addeventreq", methods=["GET", "POST"])
@sqldb
def addeventreq(c):
    if request.method == "POST":
        uuname, uemail = session.get("username"), session.get("email")
        field = ["eventname", "email", "starttime", "endtime", "eventdate", "enddate", "location", "category", "description", "username"]
        event_values = [request.form.get(y) for y in field]
        event_values[-1], event_values[1] = uuname, uemail
        check = c.execute("SELECT * FROM eventdetail WHERE eventname=(?)", (event_values[0],))
        fetchall = check.fetchall()
        for ab in fetchall:
                if all(ab[x] == y for x,y in zip(field, event_values)):
                    return "Event Already Exists"

        fetchall2 = c.execute("SELECT * FROM eventreq WHERE eventname=(?)", (event_values[0],)).fetchall()
        for ab in fetchall2:
                if all(ab[x] == y for x,y in zip(field, event_values)):
                    return "Event Already Submitted! Please Wait For Approval"

        efields = ", ".join(field)
        vals = ", ".join(["?"] * len(event_values))
        if not uuname:
            return "Please Login First To Add Event."
        desc = event_values[8]
        t = Translator()
        if t.detect(desc).lang != "en":
            translated_desc = t.translate(desc, dest="en").text
            event_values[8] = translated_desc
        c.execute(f"INSERT INTO eventreq({efields}) VALUES ({vals})", tuple(event_values))
        for x in field:
            if x not in ("email", "username"):
                session.pop(x, None)
        sendlog(f"#EventRequst \nNew Event Request: {event_values} by {uuname}")
        return "Event Registered ✅. Kindly wait for approval!"

@app.route("/show_pending_events")
@sqldb
def pendingevents(c):
    uname = session.get("username")
    if not uname:
        return "Login First"
    f = c.execute("SELECT * FROM userdetails WHERE username=?", (uname, )).fetchone()
    if f["role"] == "admin":
        c.execute("SELECT * FROM eventreq")
        pendingevents = c.fetchall()
        if not pendingevents:
            pendingevents = []
        return render_template("pendingevents.html", pendingevents=pendingevents)
    else:
        return redirect(url_for("home"))

@app.route("/deleteevent/<int:eventid>")
@sqldb
def deleteevent(c, eventid):
    uname = session.get("username")
    if not uname:
        return "Login First"
    c.execute("SELECT * FROM eventdetail WHERE eventid=?", (eventid,))
    fe = c.fetchone()
    extra = c.execute("SELECT * FROM userdetails WHERE username=?", (fe["username"], )).fetchone()
    c.execute("SELECT * FROM userdetails WHERE username=?", (uname,))
    fe2 = c.fetchone()
    if fe["username"] == uname or fe2["role"]=="admin":
        try:
            del_event(c, eventid)
            details = detailsformat(fe)
            sendmail(extra["email"], "Event Deleted", f"Hey {extra['name']}! Your event was deleted by {uname}.\n\nEvent Details:\n\n{details}\n\nThank You!")
            sendlog(f"#EventDelete \nEvent Deleted by {uname}.\nEvent Details:\n\n{details}")
            return redirect(url_for("home"))
        except Exception as e:
            sendlog(f"Error Deleting Event {eventid}: {e}")
            return f"Error: {e}"
    else:
        return redirect(url_for("home"))

@app.route("/logout")
def logout():
    u = session.pop('username')
    n = session.pop('name')
    e = session.pop('email')
    sendlog(f"User Logout: {n} ({u}) {e}")
    return redirect(url_for("home"))

@app.route("/save_draft", methods=["POST"])
def save_draft():
    field = request.form.get("field")
    value = request.form.get("value")
    if value and value.strip():
        session.permanent = True
        session[field] = value.strip()
    return "DRAFT"

@app.route("/decline_event/<int:eventid>/<path:reason>")
@sqldb
def decline_event(c, eventid, reason):
    u = session.get("username")
    if u:
        c.execute("SELECT * FROM userdetails WHERE username=?", (u, ))
        f = c.fetchone()
        if f["role"] == "admin":
            email = c.execute("SELECT * from eventreq WHERE eventid=?", (eventid, )).fetchone()
            c.execute("DELETE FROM eventreq WHERE eventid=?", (eventid, ))
            seq = c.execute("SELECT * FROM sqlite_sequence WHERE name=?", ("eventreq",)).fetchone()
            c.execute("UPDATE sqlite_sequence SET seq=? WHERE name=?", (seq["seq"], "eventdetail"))
            details = detailsformat(email)
            sendmail(email['email'], "Event Declined", f"We sorry to inform to you that your event was declined for following reason:\n{reason}.\n\nEvent Details:\n\n{details}\n\nThank You!")
            sendlog(f"#EventDecline \nEvent Declined by {u}\nReason: {reason}.\nEvent Details:\n\n{details}")

    if c.execute("SELECT eventid FROM eventreq").fetchone():
        return redirect(url_for("pendingevents"))
    else:
        return redirect(url_for("home"))

@app.route("/clearsession")
def clearsession():
    c = session.clear()
    sendlog(f"Session Cleared {c}")
    return redirect(url_for("home"))

@app.route("/dummyevent")
def dummyevent():
    # ["eventname", "email", "starttime", "endtime", "eventdate", "enddate", "location", "category", "description"]
    session.permanent = True
    session["eventname"] = random.choice(["Community Tree Plantation", "Neighborhood Blood Donation Camp", "Local Cleanliness Drive"])
    session["description"] = "Join us for a community tree plantation drive to make our neighborhood greener and healthier!"
    session["location"] = random.choice(["Central Park", "Community Center", "City Hall", "Riverside Park", "Downtown Square"])
    session["category"] = random.choice(["Tree Plantation", "Blood Donation", "Cleanliness Drive"])
    # mm/dd/yyyy
    session["eventdate"] = f"{random.randint(10,12)}/{random.randint(10,28)}/{random.randint(2025,2028)}"
    session["enddate"] = f"{random.randint(10,12)}/{random.randint(10,28)}/{random.randint(2025,2028)}"
    session["starttime"] = f"{random.randint(10,12)}:{random.randint(10,59)} AM"
    session["endtime"] = f"{random.randint(10,12)}:{random.randint(10,59)} PM"
    return "Dummy Event Added to Session"

@app.route("/api")
@sqldb
def api(c):
    events = [dict(row) for row in c.execute("SELECT * FROM eventdetail").fetchall()]
    user = dict(session)
    user_details = "No user logged in"
    if user.get("username"):
        user_details = c.execute("SELECT * FROM userdetails WHERE username=?", (user["username"],)).fetchone()
        user_details = dict(user_details)
    toreturn = {"active events": events, "current session including draft add event values": user, "current user": user_details}
    return jsonify(toreturn)

@app.route("/checkeventloop")
@sqldb
def checkeventloop(c):
    try:
        ch = c.execute("SELECT * FROM eventdetail").fetchall()
        ist = zoneinfo.ZoneInfo("Asia/Kolkata")
        hour24 = datetime.timedelta(hours=24)
        for x in ch:
            etime = datetime.datetime.strptime(f"{x['enddate']} {x['endtime']}", "%Y-%m-%d %H:%M").replace(tzinfo=ist)
            # etime = etime + hour24
            if etime <= datetime.datetime.now(ist):
                del_event(c, x["eventid"])
                details = detailsformat(x)
                sendmail(x["email"], "Event Ended", f"Hey there your event was ended, so it has been deleted!\n\nEvent Details:\n\n{details}\n\nThank You!")
                sendlog(f"#EventEnd \nEvent Ended at {etime.strftime('%Y-%m-%d %H:%M:%S')}.\nEvent Details:\n\n{details}")
        return "<h1>CHECK EVENT LOOP COMPLETED</h1>"
    except Exception as e:
        text = f"Checkk event loop error: {e}"
        sendlog(text)
        print(text)
        return text

def checkevent():
    while True:
        time.sleep(30 + random.randint(0,10))
        try:
            try:
                requests.get("https://ecocamp-3bz3.onrender.com/checkeventloop", timeout=10)
            except requests.exceptions.RequestException:
                requests.get("http://127.0.0.1:8000/checkeventloop", timeout=10)
        except Exception as e:
            print(f"Check event loop error: {e}")
            sendlog(f"Check event loop error: {e}")
            time.sleep(60)


if __name__ == "__main__":
    load_translations()
    threading.Thread(target=checkevent, name="CheckEventExist", daemon=True).start()
    threading.Thread(target=translation_file_thread, name="TranslationFileThread", daemon=True).start()
    socket.run(app, debug=True, port=8000)
