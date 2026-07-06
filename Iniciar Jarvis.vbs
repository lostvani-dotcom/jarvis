' Iniciar Jarvis.vbs
' =====================
' Abre o Jarvis (interface gráfica) com um clique duplo, sem abrir
' nenhuma janela de terminal/CMD -- usa pythonw.exe (a variante do
' Python sem console) em vez de python.exe, e roda com janela
' totalmente oculta (WshShell.Run(..., 0, ...)).
'
' Se der errado (Python não encontrado, dependência faltando, etc.),
' nada aparece na tela por design do pythonw -- nesse caso, use
' "iniciar_jarvis_com_console.bat" (mesma pasta) pra ver a mensagem
' de erro de verdade.

Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)

Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = scriptDir
shell.Run "pythonw.exe main.py", 0, False
