from . import sendlog, sendmail
from .detailformat import detailsformat


def del_event(c, eventid):
    try:
        edetail = c.execute("SELECT * FROM eventdetail WHERE eventid=?", (eventid,)).fetchone()
        details = c.execute("SELECT * FROM userdetails WHERE username=?", (edetail["username"],)).fetchone()
        c.execute("DELETE FROM eventdetail where eventid=?", (eventid,))
        c.execute("DELETE FROM messages where eventid=?", (eventid,))
        events = details["events"].split(",")
        if str(eventid) in events:
            events.remove(str(eventid))
            new = ",".join(events)
            if events == []:
                c.execute("UPDATE userdetails SET events=NULL WHERE username=?", (details["username"], ))
            else:
                c.execute("UPDATE userdetails SET events=? WHERE username=?", (new, details["username"]))
        likes = details["likes"].split(",") if details["likes"] else []
        if str(eventid) in likes:
            likes.remove(str(eventid))
            newl = ",".join(likes)
            if likes == []:
                c.execute("UPDATE userdetails SET likes=NULL WHERE username=?", (details["username"], ))
            else:
                c.execute("UPDATE userdetails SET likes=? WHERE username=?", (newl, details["username"]))
    except Exception as e:
        sendlog(f"Error Deleting Event {eventid}: {e}")


def delete_eventfromid(c, eventid, session, redirect, url_for):
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
