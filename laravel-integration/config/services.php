<?php

return [
    // ... existing services ...

    'python_cms' => [
        'url' => env('PYTHON_CMS_URL', 'http://localhost:8001'),
        'timeout' => env('PYTHON_CMS_TIMEOUT', 10),
    ],

    // ... rest of services ...
];

