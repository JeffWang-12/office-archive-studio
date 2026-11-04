$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$officeApp = $null
$officeDoc = $null
$oldUpdateLinks = $null
$result = $null
try {
    $request = [Console]::In.ReadToEnd() | ConvertFrom-Json
    if ($request.application -notin @('Word.Application', 'KWPS.Application')) { throw '不支持的 Office 组件' }
    if ($request.mode -notin @('docx', 'pdf')) { throw '不支持的目标格式' }
    $officeApp = New-Object -ComObject $request.application
    $officeApp.Visible = $false
    $officeApp.DisplayAlerts = 0
    # Never execute macros or update external links when opening imported files.
    $officeApp.AutomationSecurity = 3
    $oldUpdateLinks = $officeApp.Options.UpdateLinksAtOpen
    $officeApp.Options.UpdateLinksAtOpen = $false
    $sourcePath = [string]$request.source
    $outputPath = [string]$request.output
    $officeDoc = $officeApp.Documents.Open($sourcePath, $false, $true, $false, '', '', $false, '', '', 0, 0, $false)
    if ($request.mode -eq 'pdf') {
        $officeDoc.Repaginate()
        # Only refresh page-number fields; never update external LINK/DDE fields.
        foreach ($section in $officeDoc.Sections) {
            foreach ($footer in $section.Footers) {
                foreach ($field in $footer.Range.Fields) {
                    if ($field.Type -in @(26, 33)) { $field.Update() | Out-Null }
                }
            }
        }
        $officeDoc.ExportAsFixedFormat($outputPath, 17)
    } else {
        try { $officeDoc.SaveAs2($outputPath, 16) } catch { $officeDoc.SaveAs($outputPath, 16) }
    }
    $result = @{ ok = $true; application = $request.application; mode = $request.mode }
} catch {
    $result = @{ ok = $false; error = $_.Exception.Message }
} finally {
    if ($null -ne $officeDoc) {
        try { $officeDoc.Close(0) } catch {}
        [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($officeDoc) | Out-Null
    }
    if ($null -ne $officeApp) {
        if ($null -ne $oldUpdateLinks) { try { $officeApp.Options.UpdateLinksAtOpen = $oldUpdateLinks } catch {} }
        try { $officeApp.Quit(0) } catch {}
        [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($officeApp) | Out-Null
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
$result | ConvertTo-Json -Compress
