<?php

namespace App\Http\Controllers;

use App\Http\Controllers\Controller;
use App\Services\ChargingService;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Log;

class WebSocketController extends Controller
{
    protected $chargingService;

    public function __construct(ChargingService $chargingService)
    {
        $this->chargingService = $chargingService;
    }

    /**
     * Handle WebSocket messages from Node.js gateway
     * 
     * POST /api/websocket/message
     */
    public function handleMessage(Request $request)
    {
        try {
            $user = Auth::user();
            
            if (!$user) {
                return response()->json([
                    'success' => false,
                    'error' => 'Unauthorized',
                ], 401);
            }

            $action = $request->input('action');
            $data = $request->input('data', []);
            $userId = $request->input('userId');

            // Verify user ID matches authenticated user
            if ($userId && (int)$userId !== $user->id) {
                return response()->json([
                    'success' => false,
                    'error' => 'User ID mismatch',
                ], 403);
            }

            // Handle the message
            $result = $this->chargingService->handleWebSocketMessage($user, $action, $data);

            return response()->json($result);

        } catch (\Exception $e) {
            Log::error('Error handling WebSocket message', [
                'error' => $e->getMessage(),
                'trace' => $e->getTraceAsString(),
            ]);

            return response()->json([
                'success' => false,
                'error' => 'Internal server error',
                'message' => $e->getMessage(),
            ], 500);
        }
    }

    /**
     * Validate JWT token (called by Node.js gateway)
     * 
     * POST /api/auth/validate-token
     */
    public function validateToken(Request $request)
    {
        try {
            $token = $request->input('token');

            if (!$token) {
                return response()->json([
                    'valid' => false,
                ], 400);
            }

            // Verify token using Laravel's JWT guard
            try {
                $user = Auth::guard('api')->setToken($token)->user();
                
                if (!$user) {
                    return response()->json([
                        'valid' => false,
                    ]);
                }

                return response()->json([
                    'valid' => true,
                    'user' => [
                        'id' => $user->id,
                        'user_id' => $user->id,
                        'email' => $user->email,
                        'name' => $user->name,
                    ],
                ]);

            } catch (\Exception $e) {
                return response()->json([
                    'valid' => false,
                ]);
            }

        } catch (\Exception $e) {
            Log::error('Error validating token', [
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'valid' => false,
            ], 500);
        }
    }
}

