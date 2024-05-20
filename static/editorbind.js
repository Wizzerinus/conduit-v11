ace.config.set("basePath", "/static/lib/ace/")

class EditorBind {
    constructor(vue, editor_id, editor_mode) {
        this.editor_id = editor_id
        this.editor = ace.edit(editor_id)
        this.editor.session.setUseSoftTabs(true)
        this.editor.session.setUseWrapMode(true)
        this.editor.session.setMode(editor_mode)
        this.editor.$blockScrolling = Infinity

        this.vue = vue
        this.editor.session.on("change", () => vue.unsaved_changes = true)
        this.editor.commands.addCommand({
            name: "save",
            bindKey: {win: "Ctrl-S", mac: "Command-S"},
            exec: this.save.bind(this),
        })
    }

    teleport(where) {
        // This is a crutch that fixes Vue being not compatible with Ace for some reason
        // It's not a good solution, but it works
        const ace_editor = document.getElementById(this.editor_id)
        const ace_teleport = document.getElementById(where)
        ace_teleport.appendChild(ace_editor)
    }

    setText(text) {
        this.editor.setValue(text, -1)
        this.editor.clearSelection()
        this.editor.focus()
    }

    save(editor) {
        this.vue.saveText(editor.getValue()).then(r => {})
    }

    remove(str) {
        this.editor.find(str, {backwards: true, wrap: true})
        this.editor.replaceAll("")
    }
}
