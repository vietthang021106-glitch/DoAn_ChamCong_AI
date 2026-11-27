<?php
declare(strict_types=1);

/** Minimal, dependency-free .env loader for the PHP web process. */
final class ProjectEnvironment
{
    public static function loadFile(string $path, bool $overrideExisting = false): int
    {
        if (!is_file($path)) {
            return 0;
        }

        // On Windows, is_readable() can report false for files that PHP can
        // successfully open under the current process token. Let the actual
        // read decide; file() returns false when access is genuinely denied.
        $lines = @file($path, FILE_IGNORE_NEW_LINES);
        if (!is_array($lines)) {
            return 0;
        }

        $loaded = 0;
        foreach ($lines as $line) {
            $line = trim($line);
            if ($line === '' || str_starts_with($line, '#')) {
                continue;
            }
            if (str_starts_with($line, 'export ')) {
                $line = trim(substr($line, 7));
            }
            $separator = strpos($line, '=');
            if ($separator === false) {
                continue;
            }
            $name = trim(substr($line, 0, $separator));
            if (!preg_match('/^[A-Za-z_][A-Za-z0-9_]*$/D', $name)) {
                continue;
            }
            if (!$overrideExisting && getenv($name) !== false) {
                continue;
            }

            $value = trim(substr($line, $separator + 1));
            if ($value !== '' && ($value[0] === '"' || $value[0] === "'")) {
                $quote = $value[0];
                $end = strrpos($value, $quote);
                if ($end > 0) {
                    $value = substr($value, 1, $end - 1);
                    if ($quote === '"') {
                        $value = stripcslashes($value);
                    }
                }
            } else {
                $value = preg_replace('/\s+#.*$/', '', $value) ?? $value;
                $value = trim($value);
            }

            putenv($name . '=' . $value);
            $_ENV[$name] = $value;
            $_SERVER[$name] = $value;
            $loaded++;
        }

        return $loaded;
    }
}
