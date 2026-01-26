from . import sendlog, sendmail, detailsformat


def addevent(c, request, redirect, url_for):
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
    return redirect(url_for("home"))
