Option Explicit
Dim shell, files, root, python, command
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
root = files.GetParentFolderName(WScript.ScriptFullName)
If files.FileExists(root & "\MusicWorkshop.exe") Then
    shell.CurrentDirectory = root
    shell.Run Chr(34) & root & "\MusicWorkshop.exe" & Chr(34), 1, False
    WScript.Quit 0
End If
python = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python312\pythonw.exe"
If Not files.FileExists(python) Then
    MsgBox "Python 3.12 was not found. Run MusicWorkshop.pyw with Python 3.12.", 48, "Music Workshop"
    WScript.Quit 1
End If
If Not files.FileExists(root & "\MusicWorkshop.pyw") Then
    MsgBox "MusicWorkshop.pyw is missing next to the launcher.", 48, "Music Workshop"
    WScript.Quit 1
End If
shell.CurrentDirectory = root
command = Chr(34) & python & Chr(34) & " " & Chr(34) & root & "\MusicWorkshop.pyw" & Chr(34)
shell.Run command, 1, False
