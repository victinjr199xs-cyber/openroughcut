# Builds a small talking-head-style sample with Windows text-to-speech:
# a long pause, a filler word and an abandoned take, so every detector has
# something to find. Usage: powershell -File scripts\make_sample.ps1 [outdir]
param([string]$OutDir = "$PSScriptRoot\..\samples")

Add-Type -AssemblyName System.Speech
New-Item -ItemType Directory -Force $OutDir | Out-Null
$wav = Join-Path $OutDir "sample-voice.wav"
$mp4 = Join-Path $OutDir "sample.mp4"

$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.Rate = 0
$synth.SetOutputToWaveFile($wav)
$p = New-Object System.Speech.Synthesis.PromptBuilder
$p.AppendText("Hello everyone, and welcome back to the channel.")
$p.AppendBreak([TimeSpan]::FromSeconds(2.5))
$p.AppendText("Today we are going to.")
$p.AppendBreak([TimeSpan]::FromSeconds(0.8))
$p.AppendText("Today we are going to learn how to edit videos faster.")
$p.AppendBreak([TimeSpan]::FromSeconds(0.4))
$p.AppendText("Um,")
$p.AppendBreak([TimeSpan]::FromSeconds(0.3))
$p.AppendText("the first step is to remove the silences.")
$p.AppendBreak([TimeSpan]::FromSeconds(3))
$p.AppendText("Thanks for watching, see you next time.")
$synth.Speak($p)
$synth.Dispose()

$ffmpeg = if ($env:ORC_FFMPEG) { $env:ORC_FFMPEG } else { "ffmpeg" }
& $ffmpeg -y -v error -f lavfi -i "color=c=0x1e293b:s=1280x720:r=30" -i $wav `
    -vf "drawtext=text='OpenRoughCut sample  %{pts\:hms}':fontcolor=white:fontsize=48:x=(w-tw)/2:y=(h-th)/2" `
    -shortest -c:v libx264 -preset veryfast -pix_fmt yuv420p -c:a aac -b:a 128k $mp4
Write-Output $mp4
