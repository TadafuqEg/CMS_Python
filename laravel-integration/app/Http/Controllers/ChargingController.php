<?php

namespace App\Http\Controllers;

use App\Http\Controllers\Controller;
use App\Services\ChargingService;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Validator;

class ChargingController extends Controller
{
    protected $chargingService;

    public function __construct(ChargingService $chargingService)
    {
        $this->chargingService = $chargingService;
        $this->middleware('auth:api');
    }

    /**
     * Start charging session
     * 
     * POST /api/charging/start
     */
    public function start(Request $request)
    {
        $validator = Validator::make($request->all(), [
            'charger_id' => 'required|string',
            'connector_id' => 'sometimes|integer|min:1',
        ]);

        if ($validator->fails()) {
            return response()->json([
                'success' => false,
                'errors' => $validator->errors(),
            ], 422);
        }

        try {
            $user = Auth::user();
            $result = $this->chargingService->startCharging(
                $user,
                $request->input('charger_id'),
                $request->input('connector_id', 1)
            );

            return response()->json($result);

        } catch (\Exception $e) {
            return response()->json([
                'success' => false,
                'error' => $e->getMessage(),
            ], 400);
        }
    }

    /**
     * Stop charging session
     * 
     * POST /api/charging/stop
     */
    public function stop(Request $request)
    {
        $validator = Validator::make($request->all(), [
            'charger_id' => 'sometimes|string',
        ]);

        if ($validator->fails()) {
            return response()->json([
                'success' => false,
                'errors' => $validator->errors(),
            ], 422);
        }

        try {
            $user = Auth::user();
            $result = $this->chargingService->stopCharging(
                $user,
                $request->input('charger_id')
            );

            return response()->json($result);

        } catch (\Exception $e) {
            return response()->json([
                'success' => false,
                'error' => $e->getMessage(),
            ], 400);
        }
    }

    /**
     * Get active session
     * 
     * GET /api/charging/session/active
     */
    public function getActiveSession(Request $request)
    {
        try {
            $user = Auth::user();
            $session = $this->chargingService->getActiveSession($user);

            return response()->json([
                'success' => true,
                'session' => $session ? $session->toArray() : null,
            ]);

        } catch (\Exception $e) {
            return response()->json([
                'success' => false,
                'error' => $e->getMessage(),
            ], 500);
        }
    }

    /**
     * Get charger status
     * 
     * GET /api/charging/charger/{chargerId}/status
     */
    public function getChargerStatus(Request $request, string $chargerId)
    {
        try {
            $status = $this->chargingService->getChargerStatus($chargerId);

            return response()->json([
                'success' => true,
                'status' => $status,
            ]);

        } catch (\Exception $e) {
            return response()->json([
                'success' => false,
                'error' => $e->getMessage(),
            ], 400);
        }
    }

    /**
     * List available chargers
     * 
     * GET /api/charging/chargers
     */
    public function listChargers(Request $request)
    {
        try {
            $chargers = $this->chargingService->listAvailableChargers();

            return response()->json([
                'success' => true,
                'chargers' => $chargers,
            ]);

        } catch (\Exception $e) {
            return response()->json([
                'success' => false,
                'error' => $e->getMessage(),
            ], 500);
        }
    }
}

