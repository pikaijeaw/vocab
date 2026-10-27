param([int]$Port = 5005, [switch]$NoOpen)
# Tiny static file server for the HSK dashboard (localhost only).
$root = $PSScriptRoot
$types = @{ '.html' = 'text/html; charset=utf-8'; '.js' = 'text/javascript; charset=utf-8'; '.css' = 'text/css'; '.json' = 'application/json' }
$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://localhost:$Port/")
$listener.Start()
Write-Host "HSK dashboard running at http://localhost:$Port/  (Ctrl+C to stop)"
if (-not $NoOpen) { Start-Process "http://localhost:$Port/" }
try {
  while ($listener.IsListening) {
    $ctx = $listener.GetContext()
    $name = $ctx.Request.Url.LocalPath.TrimStart('/')
    if ($name -eq '') { $name = 'index.html' }
    $file = Join-Path $root $name
    if ((Test-Path $file -PathType Leaf) -and ((Resolve-Path $file).Path.StartsWith($root))) {
      $bytes = [IO.File]::ReadAllBytes($file)
      $ext = [IO.Path]::GetExtension($file).ToLower()
      $ctx.Response.ContentType = if ($types.ContainsKey($ext)) { $types[$ext] } else { 'application/octet-stream' }
      $ctx.Response.OutputStream.Write($bytes, 0, $bytes.Length)
    } else { $ctx.Response.StatusCode = 404 }
    $ctx.Response.Close()
  }
} finally { $listener.Stop() }
