' Starts aaron_listener.py with no console window. Resolves the project root
' from this file's own location, so it works wherever the repo is cloned.
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
Set shell = CreateObject("WScript.Shell")
shell.Run """" & root & "\venv\Scripts\pythonw.exe"" """ & root & "\src\aaron_listener.py""", 0, False
