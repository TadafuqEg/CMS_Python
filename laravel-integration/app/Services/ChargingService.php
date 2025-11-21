<?php

namespace App\Services;

use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Redis;
use Illuminate\Support\Facades\Log;
use App\Models\User;
use App\Models\ChargingSession;
use App\Models\Charger;
use Exception;

class ChargingService
{
    protected $pythonCmsUrl;
    protected $timeout;

    public function __construct()
    {
        $this->pythonCmsUrl = config('services.python_cms.url', 'http://localhost:8001');
        $this->timeout = config('services.python_cms.timeout', 10);
    }

    /**
     * Start a charging session
     */
    public function startCharging(User $user, string $chargerId, int $connectorId = 1): array
    {
        try {
            // Validate user has active subscription
            if (!$user->hasActiveSubscription()) {
                throw new Exception('User does not have an active subscription');
            }

            // Check if charger is available
            $charger = Charger::where('id', $chargerId)->first();
            if (!$charger) {
                throw new Exception('Charger not found');
            }

            if (!$charger->is_available) {
                throw new Exception('Charger is not available');
            }

            // Check if user already has an active session
            $activeSession = ChargingSession::where('user_id', $user->id)
                ->where('status', 'active')
                ->first();

            if ($activeSession) {
                throw new Exception('User already has an active charging session');
            }

            // Call Python CMS API to start charging
            $response = Http::timeout($this->timeout)
                ->post("{$this->pythonCmsUrl}/api/charging/remote_start", [
                    'charger_id' => $chargerId,
                    'id_tag' => $user->id_tag ?? $user->id,
                    'connector_id' => $connectorId,
                ]);

            if (!$response->successful()) {
                throw new Exception('Failed to start charging: ' . $response->body());
            }

            $responseData = $response->json();

            // Create session record in database
            $session = ChargingSession::create([
                'user_id' => $user->id,
                'charger_id' => $chargerId,
                'gun_id' => $connectorId,
                'status' => 'active',
                'started_at' => now(),
                'python_cms_message_id' => $responseData['message_id'] ?? null,
            ]);

            // Publish notification to Redis for real-time updates
            $this->publishNotification($user->id, [
                'type' => 'session_started',
                'session_id' => $session->id,
                'charger_id' => $chargerId,
                'message_id' => $responseData['message_id'] ?? null,
                'timestamp' => now()->toIso8601String(),
            ]);

            Log::info("Charging session started", [
                'user_id' => $user->id,
                'charger_id' => $chargerId,
                'session_id' => $session->id,
            ]);

            return [
                'success' => true,
                'session_id' => $session->id,
                'charger_id' => $chargerId,
                'message_id' => $responseData['message_id'] ?? null,
            ];

        } catch (Exception $e) {
            Log::error("Failed to start charging session", [
                'user_id' => $user->id,
                'charger_id' => $chargerId,
                'error' => $e->getMessage(),
            ]);

            throw $e;
        }
    }

    /**
     * Stop a charging session
     */
    public function stopCharging(User $user, ?string $chargerId = null): array
    {
        try {
            // Find active session for user
            $session = ChargingSession::where('user_id', $user->id)
                ->where('status', 'active');

            if ($chargerId) {
                $session->where('charger_id', $chargerId);
            }

            $session = $session->first();

            if (!$session) {
                throw new Exception('No active charging session found');
            }

            // Call Python CMS API to stop charging
            $response = Http::timeout($this->timeout)
                ->post("{$this->pythonCmsUrl}/api/charging/remote_stop", [
                    'charger_id' => $session->charger_id,
                ]);

            if (!$response->successful()) {
                throw new Exception('Failed to stop charging: ' . $response->body());
            }

            $responseData = $response->json();

            // Update session status
            $session->update([
                'status' => 'stopped',
                'stopped_at' => now(),
                'python_cms_message_id' => $responseData['message_id'] ?? null,
            ]);

            // Publish notification to Redis
            $this->publishNotification($user->id, [
                'type' => 'session_stopped',
                'session_id' => $session->id,
                'charger_id' => $session->charger_id,
                'message_id' => $responseData['message_id'] ?? null,
                'timestamp' => now()->toIso8601String(),
            ]);

            Log::info("Charging session stopped", [
                'user_id' => $user->id,
                'charger_id' => $session->charger_id,
                'session_id' => $session->id,
            ]);

            return [
                'success' => true,
                'session_id' => $session->id,
                'message_id' => $responseData['message_id'] ?? null,
            ];

        } catch (Exception $e) {
            Log::error("Failed to stop charging session", [
                'user_id' => $user->id,
                'charger_id' => $chargerId,
                'error' => $e->getMessage(),
            ]);

            throw $e;
        }
    }

    /**
     * Get charger status
     */
    public function getChargerStatus(string $chargerId): array
    {
        try {
            $response = Http::timeout($this->timeout)
                ->get("{$this->pythonCmsUrl}/api/chargers/{$chargerId}/status");

            if (!$response->successful()) {
                throw new Exception('Failed to get charger status: ' . $response->body());
            }

            return $response->json();

        } catch (Exception $e) {
            Log::error("Failed to get charger status", [
                'charger_id' => $chargerId,
                'error' => $e->getMessage(),
            ]);

            throw $e;
        }
    }

    /**
     * Get active session for user
     */
    public function getActiveSession(User $user): ?ChargingSession
    {
        return ChargingSession::where('user_id', $user->id)
            ->where('status', 'active')
            ->first();
    }

    /**
     * Get session details
     */
    public function getSessionDetails(int $sessionId, User $user): ?ChargingSession
    {
        return ChargingSession::where('id', $sessionId)
            ->where('user_id', $user->id)
            ->first();
    }

    /**
     * List available chargers
     */
    public function listAvailableChargers(): array
    {
        try {
            $response = Http::timeout($this->timeout)
                ->get("{$this->pythonCmsUrl}/api/chargers");

            if (!$response->successful()) {
                throw new Exception('Failed to list chargers: ' . $response->body());
            }

            return $response->json();

        } catch (Exception $e) {
            Log::error("Failed to list chargers", [
                'error' => $e->getMessage(),
            ]);

            throw $e;
        }
    }

    /**
     * Publish notification to Redis for real-time updates
     */
    protected function publishNotification(int $userId, array $data): void
    {
        try {
            $channels = [
                "user:{$userId}:notifications",
                "user:{$userId}:session_updates",
            ];

            foreach ($channels as $channel) {
                Redis::publish($channel, json_encode($data));
            }

        } catch (Exception $e) {
            Log::error("Failed to publish notification", [
                'user_id' => $userId,
                'error' => $e->getMessage(),
            ]);
        }
    }

    /**
     * Handle WebSocket message from Node.js gateway
     */
    public function handleWebSocketMessage(User $user, string $action, array $data): array
    {
        try {
            switch ($action) {
                case 'start_charging':
                    return $this->startCharging(
                        $user,
                        $data['charger_id'] ?? null,
                        $data['connector_id'] ?? 1
                    );

                case 'stop_charging':
                    return $this->stopCharging($user, $data['charger_id'] ?? null);

                case 'get_charger_status':
                    return $this->getChargerStatus($data['charger_id'] ?? null);

                case 'get_active_session':
                    $session = $this->getActiveSession($user);
                    return [
                        'success' => true,
                        'session' => $session ? $session->toArray() : null,
                    ];

                case 'list_chargers':
                    return [
                        'success' => true,
                        'chargers' => $this->listAvailableChargers(),
                    ];

                default:
                    throw new Exception("Unknown action: {$action}");
            }

        } catch (Exception $e) {
            Log::error("Error handling WebSocket message", [
                'user_id' => $user->id,
                'action' => $action,
                'error' => $e->getMessage(),
            ]);

            return [
                'success' => false,
                'error' => $e->getMessage(),
            ];
        }
    }
}

