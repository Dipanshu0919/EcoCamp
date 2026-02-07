from . import sendlog, sendmail, detailsformat


def addevent(c, request):
    field = ["eventname", "email", "starttime", "endtime", "eventdate", "enddate", "location", "category", "description", "username"]
    event_values = [request.form.get(y) for y in field]
    check = c.execute("SELECT * FROM eventdetail WHERE eventname=(?)", (event_values[0],))
    fetchall = check.fetchall()
    for ab in fetchall:
            if all(ab[x] == y for x,y in zip(field, event_values)):
                return "Event Already Exists"

    tuple_all, tuple_event_values = ", ".join(field), tuple(event_values)
    vals = ", ".join(["?"] * len(event_values))

    c.execute(f"INSERT INTO eventdetail({tuple_all}) VALUES ({vals})", tuple_event_values)
    lastid = c.execute("SELECT eventid FROM eventdetail ORDER BY eventid DESC LIMIT 1").fetchone()
    c.execute("DELETE FROM eventreq WHERE eventid=(?)", (lastid["eventid"], ))
    uud = c.execute("SELECT events FROM userdetails WHERE username=?", (event_values[-1], )).fetchone()
    if not uud or not uud["events"]:
        fe = []
    else:
        fe = uud["events"].split(",")
    fe.append(str(lastid["eventid"]))
    joint = ",".join(fe)
    c.execute("UPDATE userdetails SET events=? WHERE username=?", (joint, event_values[-1]))
    eventdetails = c.execute("SELECT * FROM eventdetail WHERE eventid=?", (lastid["eventid"], )).fetchone()
    details = detailsformat(eventdetails)
    sendmail(event_values[1], "Event Approved", f'Congragulations\n\nYour Event is approved and now visible on Campaigns Page.\n\nEvent Details:\n\n{details}\n\nThank You!')
    sendlog(f"#EventAdd \nNew Event Added:\n{details}")
    return "Event added!"


def addeventrequest(c, request, session):
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

    c.execute(f"INSERT INTO eventreq({efields}) VALUES ({vals})", tuple(event_values))
    for x in field:
        if x not in ("email", "username"):
            session.pop(x, None)
    sendlog(f"#EventRequst \nNew Event Request: {event_values} by {uuname}")
    return "Event Registered ✅. Kindly wait for approval!"
