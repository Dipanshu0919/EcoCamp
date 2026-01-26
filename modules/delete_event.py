from . import sendlog


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
