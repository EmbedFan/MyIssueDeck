' Stops the MyIssueDeck server started from this folder and reports the result.
Option Explicit
Dim shell, folder, code
Set shell = CreateObject("WScript.Shell")
folder = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
code = shell.Run("powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & folder & "stop-server.ps1""", 0, True)
If code = 0 Then
  MsgBox "MyIssueDeck server stopped.", vbInformation, "MyIssueDeck"
ElseIf code = 4 Then
  MsgBox "No MyIssueDeck server from this folder was running.", vbInformation, "MyIssueDeck"
Else
  MsgBox "The server could not be stopped. See logs\start.log.", vbCritical, "MyIssueDeck"
End If
