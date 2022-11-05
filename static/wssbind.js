const WebsocketMessage = "Lost connection to the websocket..."
const ConnectionMessage = "Connecting to the websocket..."

const PingPeriod = 25000
const ReconnectPeriod = 5000
const PongDelay = 2000

class WebsocketBind {
    constructor(app, path) {
        this.app = app
        this.path = path
        this.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
        setInterval(this.ping.bind(this), PingPeriod)
        this.connect()
    }

    connect() {
        if (this.ws) {
            this.ws.close()
        }
        this.ws = new WebSocket(`${this.protocol}//${document.domain}:${location.port}${this.path}`)
        this.ws.onmessage = this.onMessage.bind(this)
        setTimeout(this.clearIfConnected.bind(this), ReconnectPeriod)
        this.pinging = false
    }

    onMessage(event) {
        if (event.data === "__pong") {
            this.pinging = false
            this.app.alert.clearIf(WebsocketMessage)
            return
        }

        const data = JSON.parse(event.data)
        try {
            this.app[`ws_on${data.action}`](data)
        } catch (e) {
            this.app.alert.logError(`Socket action ${data.action} failed`, e)
        }
    }

    clearIfConnected() {
        if (this.ws && this.ws.readyState === 1) {
            this.app.alert.clearIf(ConnectionMessage)
            this.app.alert.clearIf(WebsocketMessage)
        } else {
            this.app.alert.set(ConnectionMessage, "warning")
            setTimeout(this.connect.bind(this), ReconnectPeriod)
        }
    }

    ping() {
        this.pinging = true
        if (!this.ws || this.ws.readyState !== 1) {
            this.pong()
            return
        }

        this.ws.send("__ping")
        setTimeout(this.pong.bind(this), PongDelay)
    }

    pong() {
        if (!this.pinging)
            return
        this.app.alert.set(WebsocketMessage, "danger")
        this.connect()
    }

    send(data) {
        if (!this.ws || this.ws.readyState !== 1)
            return
        if (typeof data === "object")
            this.ws.send(JSON.stringify(data))
        else
            this.ws.send(data)
    }
}
