<?php
declare(strict_types=1);

require_once __DIR__ . '/../Service/Environment.php';

function assertProjectEnvironment(bool $condition, string $message): void
{
    if (!$condition) {
        throw new RuntimeException($message);
    }
}

$path = tempnam(sys_get_temp_dir(), 'pbl4-env-test-');
if (!is_string($path)) {
    throw new RuntimeException('Could not create temporary env fixture.');
}
$names = ['PBL4_TEST_ENV_EXISTING', 'PBL4_TEST_ENV_QUOTED', 'PBL4_TEST_ENV_COMMENT'];
$old = [];
foreach ($names as $name) {
    $old[$name] = getenv($name);
}

try {
    putenv('PBL4_TEST_ENV_EXISTING=from-process');
    file_put_contents($path, "# ignored\nPBL4_TEST_ENV_EXISTING=from-file\nPBL4_TEST_ENV_QUOTED=\"value with spaces\"\nPBL4_TEST_ENV_COMMENT=value # comment\nINVALID-NAME=ignored\n");
    $loaded = ProjectEnvironment::loadFile($path);
    assertProjectEnvironment($loaded === 2, 'The loader should load only unset, valid variables.');
    assertProjectEnvironment(getenv('PBL4_TEST_ENV_EXISTING') === 'from-process', 'Process environment must take precedence.');
    assertProjectEnvironment(getenv('PBL4_TEST_ENV_QUOTED') === 'value with spaces', 'Quoted values must be parsed.');
    assertProjectEnvironment(getenv('PBL4_TEST_ENV_COMMENT') === 'value', 'Unquoted comments must be removed.');
} finally {
    foreach ($names as $name) {
        if ($old[$name] === false) {
            putenv($name);
            unset($_ENV[$name], $_SERVER[$name]);
        } else {
            putenv($name . '=' . $old[$name]);
            $_ENV[$name] = $old[$name];
            $_SERVER[$name] = $old[$name];
        }
    }
    @unlink($path);
}

echo "Project environment loader PASS\n";
