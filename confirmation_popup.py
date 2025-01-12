import PySimpleGUI as sg



def show_popup(action):
    layout = [
        [sg.Text('Are you sure you want to ' + action + '?')],
        [sg.Button('Yes', key= "-YES-"), sg.Button('No', key= "-NO-")]
    ]
    
    window = sg.Window('Confirmation', layout, size=(300, 100), modal=True, finalize=True, keep_on_top=True)
    window.bind('Y', '-YES-')
    window.bind("N", "-NO-")

    while True:
        event, values = window.read(timeout=100)
        if event.startswith("-YES-"):
            window.close()
            return True
        elif event.startswith("-NO-"):
            window.close()
            return False

