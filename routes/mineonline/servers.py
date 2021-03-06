from flask import Response, request, make_response, abort
import json
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
import hashlib
from uuid import uuid4, UUID
from utils.servers import *
from datetime import datetime, timedelta, timezone
from pymongo import IndexModel, ASCENDING, DESCENDING, errors
import sys
from utils.versions import get_versions
from utils.database import getclassicservers
from uuid import uuid4, UUID

def register_routes(app, mongo):
    @app.route("/api/servers/<uuid>", methods=["DELETE"])
    @app.route("/mineonline/servers/<uuid>", methods=["DELETE"])
    def deleteserver(uuid):
        mongo.db.classicservers.delete_one({"uuid": str(UUID(uuid))})
        return Response("ok", 200)

    @app.route("/api/servers/stats", methods=["GET"])
    def serverstats():
        servers = getclassicservers(mongo)
        servercount = len(servers)
        playercount = 0
        for server in servers:
            if "users" in server:
                playercount += int(server["users"])

        return Response(json.dumps({
            "serverCount": servercount,
            "playerCount": playercount
        }))

    @app.route("/api/servers", methods=["POST"])
    @app.route("/mineonline/servers", methods=["POST"])
    def addserver():
        port = request.json['port']
        maxUsers = request.json['max']
        name = request.json['name']
        onlinemode = request.json['onlinemode']
        md5 = request.json['md5']
        whitelisted = request.json['whitelisted']
        whitelistUsers = request.json['whitelistUsers']
        whitelistIPs = request.json['whitelistIPs']
        whitelistUUIDs = request.json['whitelistUUIDs']
        bannedUsers = request.json['bannedUsers']
        bannedIPs = request.json['bannedIPs']
        bannedUUIDs = request.json['bannedUUIDs']
        uuid = str(uuid4())

        players = []
        if("players" in request.json):
            players = request.json["players"]

        versionName = "Unknown Version"

        if 'ip' in request.json and request.json['ip'] != '':
            ip = request.json['ip'] # new to mineonline to allow classic servers on different IPs
        else:
            ip = request.remote_addr

        if ip == "127.0.0.1":
            return Response("Can't list local servers.", 400)

        owner = None
        ownerUUID = None

        if "owner" in request.json and request.json["owner"] != "":
            owner = request.json["owner"]
            try:
                users = mongo.db.users
                ownerUUID = users.find_one({"user": request.json["owner"]})["uuid"]
            except:
                pass

        classicservers = mongo.db.classicservers

        if(port == None):
            port = "25565"

        versions = get_versions()

        for version in versions:
            if(version["md5"] == md5 and version["type"] == "server"):
                if('clientName' in version):
                    versionName = version["clientName"]
                elif('clientVersions' in version):
                    versionName = str(version["clientVersions"]).replace("'", "").replace("[", "").replace("]", "")
                else:
                    versionName = version["name"]
            pass

        try:
            # Find an existing salted server
            currentlisting = classicservers.find_one({"port": port, "ip": ip})
            expireDuration = timedelta(minutes = 2)

            # Delete existing server record
            classicservers.delete_many({"port": port, "ip": ip})

            users = request.json['users'] if 'users' in request.json else 0

            while(True):
                cursor = classicservers.find_one(sort = [("realmId", DESCENDING)])
                seq = cursor["realmId"] + 1 if cursor != None and "realmId" in cursor and cursor["realmId"] != None else 1

                try:
                    classicservers.insert_one({
                        "salt": currentlisting["salt"] if currentlisting != None and "salt" in currentlisting else None,
                        "realmId": currentlisting["realmId"] if currentlisting != None and "realmId" in currentlisting else seq,
                        "createdAt": datetime.utcnow(),
                        "expiresAt": datetime.now(timezone.utc) + expireDuration,
                        "ip": ip,
                        "port": port,
                        "users": users,
                        "maxUsers": maxUsers,
                        "name": name,
                        "onlinemode": onlinemode,
                        "versionName": versionName,
                        "md5": md5,
                        "whitelisted": whitelisted,
                        "whitelistUsers": whitelistUsers,
                        "whitelistIPs": whitelistIPs,
                        "whitelistUUIDs": whitelistUUIDs,
                        "bannedUsers": bannedUsers,
                        "bannedIPs": bannedIPs,
                        "bannedUUIDs": bannedUUIDs,
                        "players": players,
                        "ownerUUID": ownerUUID,
                        "owner": owner,
                        "uuid": uuid
                    })
                except errors.WriteError as writeError:
                    if writeError.code == 11000:
                        continue
                    else:
                        return Response("Something went wrong.", 500)

                break
                        
            return make_response(json.dumps({
                "uuid": uuid
            }), 200)

        except Exception as e:
            return Response("Something went wrong.", 500)

        return Response("Something went wrong.", 500)

    @app.route("/api/servers", methods=["GET"])
    @app.route("/mineonline/servers", methods=["GET"])
    def listservers():
        sessionId = request.args.get('sessionId')
        username = request.args.get('username')
        uuid = request.args.get('uuid')

        user = None

        if "sessionId" in request.args:
            try:
                users = mongo.db.users
                user = users.find_one({"sessionId": ObjectId(sessionId)})
            except:
                pass
        elif "username" in request.args or "uuid" in request.args:
            user = {
                "user": username,
                "uuid": uuid
            }
            return Response("Invalid Session", 401)

        if (user == None):
            return Response("Invalid Session", 401)

        mineOnlineServers = getclassicservers(mongo)
        featuredServers = list(mongo.db.featuredservers.find())
        featuredServers = [dict(server, **{'isMineOnline': False}) for server in featuredServers]
        servers = mineOnlineServers + featuredServers

        def mapServer(x): 
            if(not"md5" in x):
                return
            if(not "whitelisted" in x):
                return

            if ("public" in x and x["public"] == False):
                return

            status = NONE

            if (x["onlinemode"] == False):
                status = OFFLINEMODE

            if not user == None:
                if (x["whitelisted"] == True and "whitelistUsers" in x and "whitelistIPs" in x and "whitelistUUIDs" in x):
                    if(user["user"] in x["whitelistUsers"] or request.remote_addr in x["whitelistIPs"]):
                        status = ON_THE_WHITELIST
                    else:
                        status = NOT_ON_THE_WHITELIST

                if ("bannedUsers" in x and "bannedIPs" in x and "bannedUUIDs" in x and (user["user"] in x["bannedUsers"] or request.remote_addr in x["bannedIPs"] or user["uuid"] in x["bannedUUIDs"])):
                    status = BANNED

            return { 
                "createdAt": str(x["createdAt"]) if "createdAt" in x else None,
                "ip": x["ip"] if status != BANNED and status != NOT_ON_THE_WHITELIST else None,
                "port": x["port"] if status != BANNED and status != NOT_ON_THE_WHITELIST else None,
                "users": x["users"] if "users" in x else "0",
                "maxUsers": x["maxUsers"] if "maxUsers" in x else "24",
                "name": x["name"],
                "onlinemode": x["onlinemode"],
                "md5": x["md5"],
                "isMineOnline": x["isMineOnline"] if "isMineOnline" in x else True,
                "status": status,
                "players": x["players"] if "players" in x else []
            }

        servers = list(map(mapServer, servers))
        servers = list(filter(filterServer, servers))

        return Response(json.dumps(servers))

    @app.route("/api/getserver", methods=["GET"])
    @app.route("/mineonline/getserver", methods=["GET"])
    def getserver():
        serverIP = request.args.get('serverIP')
        serverPort = request.args.get('serverPort')

        if(serverPort == None):
            serverPort = "25565"

        try:
            server = mongo.db.classicservers.find_one({"port": serverPort, "ip": serverIP})
        except:
            pass

        if server == None:
            try:
                server = mongo.db.featuredservers.find_one({"port": serverPort, "ip": serverIP})
            except:
                pass

        if server == None:
            return Response("Server not found.", 404)
        
        def mapServer(x): 
            return { 
                "createdAt": str(x["createdAt"]) if "createdAt" in x else None,
                "ip": x["ip"],
                "port": x["port"],
                "users": x["users"] if "users" in x else "0",
                "maxUsers": x["maxUsers"] if "maxUsers" in x else "24",
                "name": x["name"],
                "onlinemode": x["onlinemode"],
                "md5": x["md5"],
                "isMineOnline": x["isMineOnline"] if "isMineOnline" in x else True,
                "players": x["players"] if "players" in x else []
            }

        return Response(json.dumps(mapServer(server)))

    # Classic authentication route.
    # Modified for mineonline.
    @app.route('/api/servertoken')
    @app.route('/mineonline/servertoken')
    @app.route('/mineonline/mppass.jsp')
    def getmmpass():
        sessionId = request.args['sessionId']
        serverIP = request.args['serverIP']
        serverPort = request.args['serverPort']

        try:
            users = mongo.db.users
            user = users.find_one({"sessionId": ObjectId(sessionId)})
        except:
            return Response("User not found.", 404)

        if (user == None):
            return Response("User not found.", 404)

        try:
            server = mongo.db.classicservers.find_one({"ip": serverIP, "port": serverPort})
        except:
            return Response("Server not found.", 404)

        if server:
            if "salt" in server:
                mppass = str(hashlib.md5((server['salt'] + user['user']).encode('utf-8')).hexdigest())
                return Response(mppass)
            else:
                return Response("Classic server not found.", 404)
        else:
            return Response("Server not found.", 404)

        return Response("Something went wrong!", 500)