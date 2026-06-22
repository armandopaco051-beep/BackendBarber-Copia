$hostName = "127.0.0.1"
$port = 6379

$result = Test-NetConnection $hostName -Port $port
if ($result.TcpTestSucceeded) {
    Write-Host "Redis OK en $hostName`:$port"
    exit 0
}

Write-Host "Redis no esta corriendo en $hostName`:$port"
Write-Host "Instala Redis/Memurai o configura CELERY_BROKER_URL con una URL Redis remota."
exit 1
