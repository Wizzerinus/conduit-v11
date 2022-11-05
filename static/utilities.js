class AlertModule {
    constructor() {
        this.alert = ""
        this.style = "info"
        this.allow_html = false
    }

    clear() {
        this.alert = ""
    }

    clearIf(val) {
        if (this.alert === val)
            this.clear()
    }

    set(alert, style, allow_html = false) {
        this.alert = alert
        this.style = style
        this.allow_html = allow_html
    }

    logError(base_text, e1, level = "danger") {
        let content = e1
        try {
            content = e1.response.data.detail
        } catch(e2) {}
        if (!content)
            content = e1
        this.set(`${base_text}: ${content}`, level)
    }
}
