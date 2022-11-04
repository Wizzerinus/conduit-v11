ace.config.set("basePath", "https://cdnjs.cloudflare.com/ajax/libs/ace/1.12.5/")

class EditorBind {
    constructor(vue, editor_id, editor_mode) {
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
