<?php

use Illuminate\Support\Facades\Route;
use App\Http\Controllers\ChargingController;
use App\Http\Controllers\WebSocketController;

// ... existing routes ...

// WebSocket message handling (called by Node.js gateway)
Route::post('/websocket/message', [WebSocketController::class, 'handleMessage'])
    ->middleware('auth:api');

// Token validation (called by Node.js gateway)
Route::post('/auth/validate-token', [WebSocketController::class, 'validateToken']);

// Charging endpoints
Route::prefix('charging')->middleware('auth:api')->group(function () {
    Route::post('/start', [ChargingController::class, 'start']);
    Route::post('/stop', [ChargingController::class, 'stop']);
    Route::get('/session/active', [ChargingController::class, 'getActiveSession']);
    Route::get('/charger/{chargerId}/status', [ChargingController::class, 'getChargerStatus']);
    Route::get('/chargers', [ChargingController::class, 'listChargers']);
});

