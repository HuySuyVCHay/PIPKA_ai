# Speaks text with the built-in Russian Windows voice (no extra software needed).
# The text comes from a UTF-8 file whose path is in the PIPKA_TTS_FILE variable.
# Exit codes: 0 - done, 3 - no Russian voice installed, 1 - any other error.
$ErrorActionPreference = 'Stop'
try {
    Add-Type -AssemblyName System.Speech
    $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
    $voice = $synth.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -like 'ru*' } | Select-Object -First 1
    if ($null -eq $voice) { exit 3 }
    $synth.SelectVoice($voice.VoiceInfo.Name)
    $synth.Volume = 100
    $culture = $voice.VoiceInfo.Culture.Name

    $text = [System.IO.File]::ReadAllText($env:PIPKA_TTS_FILE, [System.Text.Encoding]::UTF8)
    $pitch = $env:PIPKA_TTS_PITCH
    if (-not $pitch) { $pitch = 'x-low' }
    $rate = $env:PIPKA_TTS_RATE
    if (-not $rate) { $rate = 'slow' }

    $escaped = [System.Security.SecurityElement]::Escape($text)
    $ssml = "<speak version=`"1.0`" xmlns=`"http://www.w3.org/2001/10/synthesis`" xml:lang=`"$culture`"><prosody pitch=`"$pitch`" rate=`"$rate`">$escaped</prosody></speak>"

    try {
        $synth.SpeakSsml($ssml)
    } catch {
        $synth.Speak($text)
    }
    exit 0
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
