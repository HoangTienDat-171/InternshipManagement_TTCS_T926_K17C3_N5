param(
    [Parameter(Mandatory = $true)][string]$BackupPath,
    [Parameter(Mandatory = $true)][string]$ExpectedSha256,
    [Parameter(Mandatory = $true)][ValidateRange(1, 2147483647)][int]$BackupJobId,
    [Parameter(Mandatory = $true)][ValidatePattern('^ims_restore_drill_[A-Za-z0-9_]{1,48}$')][string]$RestoreDatabase,
    [Parameter(Mandatory = $true)][ValidateRange(1, 2147483647)][int]$ActorUserId,
    [switch]$UsePrecreatedRestoreDatabase,
    [string]$MysqlClient = ''
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$envFiles = @(
    (Join-Path $env:LOCALAPPDATA 'IMS-US37-CLEAN-UAT\runtime.env'),
    (Join-Path $repoRoot 'backend/.env')
)
$envFile = $envFiles | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1

# Load only database settings needed by this process; do not import SMTP or HRM secrets.
if ($envFile) {
    foreach ($line in Get-Content -LiteralPath $envFile) {
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$' -and -not $line.TrimStart().StartsWith('#')) {
            $key = $Matches[1]
            if ($key -notin @('MYSQL_HOST', 'MYSQL_PORT', 'MYSQL_USER', 'MYSQL_PASSWORD', 'MYSQL_DATABASE')) { continue }
            $value = $Matches[2].Trim().Trim('"').Trim("'")
            if (-not [Environment]::GetEnvironmentVariable($key, 'Process')) {
                [Environment]::SetEnvironmentVariable($key, $value, 'Process')
            }
        }
    }
}

foreach ($name in @('MYSQL_HOST', 'MYSQL_PORT', 'MYSQL_USER', 'MYSQL_PASSWORD', 'MYSQL_DATABASE')) {
    if (-not [Environment]::GetEnvironmentVariable($name, 'Process')) { throw "Thiếu $name trong backend/.env hoặc môi trường hiện tại." }
}
if ($env:MYSQL_DATABASE -notmatch '(?i)(uat|test|dev)') { throw 'Restore drill chỉ chạy khi source MYSQL_DATABASE có tên UAT/test/dev.' }
if ($RestoreDatabase -eq $env:MYSQL_DATABASE) { throw 'Database restore phải khác database nguồn đang chạy.' }
if ($ExpectedSha256 -notmatch '^[A-Fa-f0-9]{64}$') { throw 'ExpectedSha256 phải là SHA-256 gồm 64 ký tự hex.' }

$BackupPath = (Resolve-Path -LiteralPath $BackupPath).Path
if (-not (Test-Path -LiteralPath $BackupPath -PathType Leaf)) { throw 'Không tìm thấy file backup.' }
$actualHash = (Get-FileHash -LiteralPath $BackupPath -Algorithm SHA256).Hash
if ($actualHash -ne $ExpectedSha256.ToUpperInvariant()) { throw 'Checksum file backup không khớp. Dừng restore.' }
$restoreUploadsDirectory = Join-Path (Split-Path $BackupPath -Parent) ("restore-drills\$RestoreDatabase")
if (Test-Path -LiteralPath $restoreUploadsDirectory) { throw "Thư mục restore đã tồn tại: $restoreUploadsDirectory. Chọn schema mới để không ghi đè." }

if (-not $MysqlClient) {
    $client = Get-Command mysql.exe -ErrorAction SilentlyContinue
    if ($client) { $MysqlClient = $client.Source }
    else {
        $mysqlCandidate = Get-ChildItem -Path "$env:ProgramFiles\MySQL" -Filter mysql.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $mysqlCandidate) { throw 'Không tìm thấy mysql.exe. Cài MySQL Client hoặc truyền -MysqlClient.' }
        $MysqlClient = $mysqlCandidate.FullName
    }
}

$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("ims-us41-restore-" + [guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $tempRoot
$cnfPath = Join-Path $tempRoot 'mysql-client.cnf'
$identity = (whoami).Trim()
function ConvertTo-MySqlCnfValue([string]$value) {
    return '"' + $value.Replace('\', '\\').Replace('"', '\"') + '"'
}

try {
    $cnf = @(
        '[client]',
        "host=$(ConvertTo-MySqlCnfValue $env:MYSQL_HOST)",
        "port=$(ConvertTo-MySqlCnfValue $env:MYSQL_PORT)",
        "user=$(ConvertTo-MySqlCnfValue $env:MYSQL_USER)",
        "password=$(ConvertTo-MySqlCnfValue $env:MYSQL_PASSWORD)",
        'default-character-set=utf8mb4'
    ) -join "`n"
    [IO.File]::WriteAllText($cnfPath, $cnf, [Text.UTF8Encoding]::new($false))
    & icacls $cnfPath '/inheritance:r' '/grant:r' "$identity`:F" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Không thiết lập được quyền riêng cho file thông tin kết nối tạm.' }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($BackupPath)
    try {
        foreach ($entry in $zip.Entries) {
            $parts = $entry.FullName.Replace('\', '/').Split('/')
            if ($entry.FullName.StartsWith('/') -or $parts -contains '..' -or $entry.FullName -match '^[A-Za-z]:') {
                throw 'Backup chứa đường dẫn không an toàn; dừng giải nén.'
            }
        }
        $manifestEntry = $zip.GetEntry('manifest.json')
        $dumpEntry = $zip.GetEntry('database.sql')
        if (-not $manifestEntry -or -not $dumpEntry) { throw 'Backup không chứa manifest.json và database.sql MySQL.' }
        $reader = [IO.StreamReader]::new($manifestEntry.Open(), [Text.Encoding]::UTF8)
        try { $manifest = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
        if ($manifest.database_backend -ne 'mysql') { throw 'Backup này không phải MySQL.' }
        if ([string]$manifest.database_name -notmatch '(?i)(uat|test|dev)') { throw 'Backup source không được đánh dấu UAT/test/dev.' }
        if ([string]$manifest.database_name -ne $env:MYSQL_DATABASE) { throw 'Backup không thuộc đúng database UAT đang cấu hình.' }
        if ($manifest.database_name -eq $RestoreDatabase) { throw 'Schema đích trùng schema nguồn trong manifest.' }

        foreach ($entry in $zip.Entries) {
            if (-not $entry.FullName.StartsWith('uploads/')) { continue }
            $relative = $entry.FullName.Substring('uploads/'.Length)
            $target = [IO.Path]::GetFullPath((Join-Path (Join-Path $tempRoot 'payload') $entry.FullName.Replace('/', [IO.Path]::DirectorySeparatorChar)))
            $payloadRoot = [IO.Path]::GetFullPath((Join-Path $tempRoot 'payload'))
            if (-not $target.StartsWith($payloadRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'Đường dẫn uploads nằm ngoài thư mục tạm.' }
            if ($entry.FullName.EndsWith('/')) { $null = New-Item -ItemType Directory -Force -Path $target; continue }
            $null = New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent)
            $source = $entry.Open()
            $destination = [IO.File]::Create($target)
            try { $source.CopyTo($destination) } finally { $destination.Dispose(); $source.Dispose() }
        }
        $dumpPath = Join-Path $tempRoot 'database.sql'
        $dumpStream = $dumpEntry.Open()
        $dumpFile = [IO.File]::Create($dumpPath)
        try { $dumpStream.CopyTo($dumpFile) } finally { $dumpFile.Dispose(); $dumpStream.Dispose() }
    } finally { $zip.Dispose() }

    $sourceJobSql = "SELECT status, backup_type, file_name, checksum_sha256 FROM IMS_BACKUP_JOBS WHERE id=$BackupJobId LIMIT 1"
    $sourceJobText = & $MysqlClient "--defaults-extra-file=$cnfPath" '--batch' '--raw' '--skip-column-names' '--database' $env:MYSQL_DATABASE '--execute' $sourceJobSql 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'Không đọc được job backup nguồn từ MySQL UAT.' }
    $sourceJob = @($sourceJobText -split "`t")
    if ($sourceJob.Count -ne 4 -or $sourceJob[0] -ne 'SUCCESS' -or $sourceJob[1] -notin @('MANUAL', 'SCHEDULED') -or $sourceJob[2] -ne (Split-Path $BackupPath -Leaf) -or $sourceJob[3] -ne $actualHash.ToLowerInvariant()) {
        throw 'Job backup, tên file hoặc checksum không khớp bản ghi SUCCESS trong database UAT.'
    }
    if ($ActorUserId -gt 0) {
        $actorCount = & $MysqlClient "--defaults-extra-file=$cnfPath" '--batch' '--skip-column-names' '--database' $env:MYSQL_DATABASE '--execute' "SELECT COUNT(*) FROM NGUOI_DUNG WHERE ma_nguoi_dung=$ActorUserId AND vai_tro='Admin' AND trang_thai='HoatDong'" 2>$null
        if ($LASTEXITCODE -ne 0 -or [int]$actorCount -ne 1) { throw 'ActorUserId không phải tài khoản Admin đang hoạt động trong UAT.' }
    }

    $schemaCheck = & $MysqlClient "--defaults-extra-file=$cnfPath" '--batch' '--skip-column-names' '--execute' "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='$RestoreDatabase'" 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'Không kết nối được MySQL để kiểm tra schema đích.' }
    if ($schemaCheck) {
        if (-not $UsePrecreatedRestoreDatabase) { throw "Schema đích $RestoreDatabase đã tồn tại. Không ghi đè; hãy chọn tên mới chưa dùng." }
        $existingTableCount = & $MysqlClient "--defaults-extra-file=$cnfPath" '--batch' '--skip-column-names' '--execute' "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='$RestoreDatabase'" 2>$null
        if ($LASTEXITCODE -ne 0 -or [int]$existingTableCount -ne 0) { throw 'Schema restore DBA tạo sẵn phải rỗng; script sẽ không ghi đè bảng hiện có.' }
    } else {
        if ($UsePrecreatedRestoreDatabase) { throw 'Không tìm thấy schema restore DBA tạo sẵn. Tạo đúng schema và cấp quyền riêng trước khi chạy lại.' }
        $createSql = "CREATE DATABASE ``$RestoreDatabase`` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;"
        & $MysqlClient "--defaults-extra-file=$cnfPath" '--execute' $createSql 2>$null
        if ($LASTEXITCODE -ne 0) { throw 'Không tạo được schema restore. Nhờ DBA tạo một schema ims_restore_drill_* rỗng và chỉ cấp quyền trên schema đó cho tài khoản backend.' }
    }

    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $MysqlClient
    $start.UseShellExecute = $false
    $start.RedirectStandardInput = $true
    $start.RedirectStandardError = $true
    $start.RedirectStandardOutput = $true
    $start.Arguments = '--defaults-extra-file="' + $cnfPath + '" --database "' + $RestoreDatabase + '"'
    $process = [Diagnostics.Process]::Start($start)
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $sourceFile = [IO.File]::OpenRead($dumpPath)
    try { $sourceFile.CopyTo($process.StandardInput.BaseStream) } finally { $sourceFile.Dispose(); $process.StandardInput.Close() }
    $process.WaitForExit()
    $null = $stderrTask.Result
    $null = $stdoutTask.Result
    if ($process.ExitCode -ne 0) { throw "MySQL import thất bại (exit $($process.ExitCode)). Schema thử được giữ lại để kiểm tra; không bị xóa tự động." }

    $checks = @()
    foreach ($table in $manifest.tables) {
        if ($table -notmatch '^[A-Za-z0-9_$]{1,64}$') { throw 'Tên bảng trong manifest không hợp lệ.' }
        $expectedCount = $manifest.table_row_counts.PSObject.Properties[$table]
        if (-not $expectedCount) { throw "Manifest thiếu số dòng của bảng $table." }
        $expected = [int64]$expectedCount.Value
        $countSql = "SELECT COUNT(*) FROM ``$table``;"
        $actualText = & $MysqlClient "--defaults-extra-file=$cnfPath" '--batch' '--skip-column-names' '--database' $RestoreDatabase '--execute' $countSql 2>$null
        if ($LASTEXITCODE -ne 0) { throw "Không kiểm tra được số dòng của bảng $table." }
        $actual = [int64]$actualText
        if ($actual -ne $expected) { throw "Số dòng không khớp ở bảng $table (manifest=$expected, restore=$actual)." }
        $checks += [pscustomobject]@{ table = $table; row_count = $actual; result = 'PASS' }
    }

    $fkQuery = "SELECT TABLE_NAME, CONSTRAINT_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME, ORDINAL_POSITION FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA='$RestoreDatabase' AND REFERENCED_TABLE_NAME IS NOT NULL ORDER BY TABLE_NAME, CONSTRAINT_NAME, ORDINAL_POSITION"
    $fkLines = & $MysqlClient "--defaults-extra-file=$cnfPath" '--batch' '--raw' '--skip-column-names' '--execute' $fkQuery 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'Không kiểm tra được danh sách khóa ngoại trong schema restore.' }
    $foreignKeys = @{}
    foreach ($line in $fkLines) {
        if (-not $line) { continue }
        $values = $line -split "`t"
        if ($values.Count -ne 6) { throw 'Kết quả kiểm tra khóa ngoại không hợp lệ.' }
        $record = [pscustomobject]@{ table = $values[0]; constraint = $values[1]; column = $values[2]; parent = $values[3]; parent_column = $values[4]; ordinal = [int]$values[5] }
        foreach ($identifier in @($record.table, $record.column, $record.parent, $record.parent_column)) {
            if ($identifier -notmatch '^[A-Za-z0-9_$]{1,64}$') { throw 'Tên bảng/cột trong khóa ngoại không an toàn.' }
        }
        $key = "$($record.table)|$($record.constraint)|$($record.parent)"
        if (-not $foreignKeys.ContainsKey($key)) { $foreignKeys[$key] = @() }
        $foreignKeys[$key] += $record
    }
    if ($null -ne $manifest.foreign_key_constraints -and $foreignKeys.Count -ne [int]$manifest.foreign_key_constraints) {
        throw "Số khóa ngoại không khớp (manifest=$($manifest.foreign_key_constraints), restore=$($foreignKeys.Count))."
    }
    foreach ($group in $foreignKeys.Values) {
        $group = @($group | Sort-Object ordinal)
        $child = [string]$group[0].table
        $parent = [string]$group[0].parent
        $joins = @(); $nonnull = @()
        foreach ($column in $group) {
            $joins += "c.``$($column.column)``=p.``$($column.parent_column)``"
            $nonnull += "c.``$($column.column)`` IS NOT NULL"
        }
        $orphanSql = "SELECT COUNT(*) FROM ``$child`` c LEFT JOIN ``$parent`` p ON $($joins -join ' AND ') WHERE $($nonnull -join ' AND ') AND p.``$($group[0].parent_column)`` IS NULL"
        $orphanCount = & $MysqlClient "--defaults-extra-file=$cnfPath" '--batch' '--skip-column-names' '--database' $RestoreDatabase '--execute' $orphanSql 2>$null
        if ($LASTEXITCODE -ne 0) { throw "Không kiểm tra được quan hệ khóa ngoại $($group[0].constraint)." }
        if ([int64]$orphanCount -ne 0) { throw "Phát hiện $orphanCount bản ghi mồ côi ở khóa ngoại $($group[0].constraint)." }
    }

    foreach ($file in $manifest.upload_files) {
        if (-not $file.path -or $file.path.StartsWith('/') -or $file.path.StartsWith('\\') -or $file.path.Contains(':') -or $file.path.Replace('\', '/').Split('/') -contains '..') {
            throw 'Manifest chứa đường dẫn upload không an toàn.'
        }
        $path = Join-Path (Join-Path $tempRoot 'payload/uploads') ($file.path.Replace('/', [IO.Path]::DirectorySeparatorChar))
        $uploadRoot = [IO.Path]::GetFullPath((Join-Path $tempRoot 'payload/uploads'))
        $fullUploadPath = [IO.Path]::GetFullPath($path)
        if (-not $fullUploadPath.StartsWith($uploadRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Đường dẫn upload nằm ngoài thư mục restore tạm.' }
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Thiếu file upload $($file.path) trong archive." }
        $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($hash -ne [string]$file.sha256) { throw "Checksum upload không khớp: $($file.path)." }
    }

    $reportPath = Join-Path (Split-Path $BackupPath -Parent) ("restore-verification-" + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.json')
    $null = New-Item -ItemType Directory -Path $restoreUploadsDirectory
    $payloadUploads = Join-Path $tempRoot 'payload/uploads'
    if (Test-Path -LiteralPath $payloadUploads) {
        Get-ChildItem -LiteralPath $payloadUploads -Force | Copy-Item -Destination $restoreUploadsDirectory -Recurse -Force
    }

    $verification = [pscustomobject]@{
        result = 'PASS'
        verified_at = (Get-Date).ToString('o')
        source_database = [string]$manifest.database_name
        restore_database = $RestoreDatabase
        backup_sha256 = $actualHash.ToLowerInvariant()
        tables = $checks
        upload_files = @($manifest.upload_files).Count
        foreign_key_constraints = $foreignKeys.Count
        restored_upload_directory = $restoreUploadsDirectory
        source_backup_id = $BackupJobId
    }
    $verification | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $reportPath -Encoding UTF8

    $actorSql = [string]$ActorUserId
    $jobJson = ($verification | ConvertTo-Json -Depth 6 -Compress).Replace("'", "''")
    $auditJson = ([pscustomobject]@{
        source_backup_id = $BackupJobId
        restore_database = $RestoreDatabase
        table_count = $checks.Count
        foreign_key_constraints = $foreignKeys.Count
        upload_file_count = @($manifest.upload_files).Count
        checksum_status = 'VALID'
    } | ConvertTo-Json -Compress).Replace("'", "''")
    $recordSql = @"
START TRANSACTION;
INSERT INTO IMS_BACKUP_JOBS (backup_type,status,started_by,started_at,finished_at,checksum_sha256,checksum_status,checksum_checked_at,manifest)
VALUES ('RESTORE_VERIFICATION','SUCCESS',$actorSql,CURRENT_TIMESTAMP(6),CURRENT_TIMESTAMP(6),'$($actualHash.ToLowerInvariant())','VALID',CURRENT_TIMESTAMP(6),CAST('$jobJson' AS JSON));
INSERT INTO IMS_AUDIT_LOG (actor_user_id,actor_name,action,resource,resource_id,outcome,metadata,created_at)
VALUES ($actorSql,(SELECT ho_ten FROM NGUOI_DUNG WHERE ma_nguoi_dung=$actorSql),'BACKUP_RESTORE_VERIFIED','BACKUP','$BackupJobId','SUCCESS',CAST('$auditJson' AS JSON),CURRENT_TIMESTAMP(6));
COMMIT;
"@
    & $MysqlClient "--defaults-extra-file=$cnfPath" '--database' $env:MYSQL_DATABASE '--execute' $recordSql 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'Restore đã qua kiểm tra nhưng không ghi được kết quả/audit vào IMS UAT. Schema thử và uploads vẫn được giữ.' }
    Write-Host "RESTORE DRILL PASS: $RestoreDatabase"
    Write-Host "Báo cáo kiểm tra: $reportPath"
    Write-Host "Uploads restore: $restoreUploadsDirectory"
    Write-Host 'Schema thử và uploads được giữ lại để kiểm tra thủ công; script không xóa schema hoặc file nào.'
}
finally {
    $tempRootFull = [IO.Path]::GetFullPath($tempRoot)
    $systemTempFull = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    if ($tempRootFull.StartsWith($systemTempFull, [StringComparison]::OrdinalIgnoreCase) -and
        (Split-Path $tempRootFull -Leaf).StartsWith('ims-us41-restore-', [StringComparison]::Ordinal)) {
        if (Test-Path -LiteralPath $tempRootFull) { Remove-Item -LiteralPath $tempRootFull -Recurse -Force }
    } else {
        Write-Warning 'Temporary restore path was not within the expected system temp folder; it was left in place.'
    }
}
