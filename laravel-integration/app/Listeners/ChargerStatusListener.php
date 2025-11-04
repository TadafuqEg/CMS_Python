<?php

namespace App\Listeners;

use Illuminate\Support\Facades\Redis;
use Illuminate\Support\Facades\Log;
use App\Models\ChargingSession;

class ChargerStatusListener
{
    /**
     * Handle charger status updates from Python CMS
     * This listener subscribes to Redis channels for charger events
     */
    public function handle($event)
    {
        try {
            $eventData = is_array($event) ? $event : $event->toArray();
            
            // Extract event type and data
            $eventType = $eventData['event'] ?? $eventData['type'] ?? null;
            $chargerId = $eventData['charger_id'] ?? null;
            
            if (!$eventType || !$chargerId) {
                return;
            }

            // Find all users with active sessions on this charger
            $activeSessions = ChargingSession::where('charger_id', $chargerId)
                ->where('status', 'active')
                ->with('user')
                ->get();

            // Notify each user about the charger status change
            foreach ($activeSessions as $session) {
                $this->notifyUser($session->user_id, [
                    'type' => 'charger_status_changed',
                    'charger_id' => $chargerId,
                    'status' => $eventData['status'] ?? null,
                    'event' => $eventType,
                    'data' => $eventData,
                    'timestamp' => now()->toIso8601String(),
                ]);
            }

            Log::info("Charger status updated", [
                'charger_id' => $chargerId,
                'event_type' => $eventType,
                'notified_users' => $activeSessions->count(),
            ]);

        } catch (\Exception $e) {
            Log::error("Error handling charger status update", [
                'error' => $e->getMessage(),
                'event' => $event,
            ]);
        }
    }

    /**
     * Notify user via Redis pub/sub
     */
    protected function notifyUser(int $userId, array $data): void
    {
        try {
            $channels = [
                "user:{$userId}:notifications",
                "user:{$userId}:charger_updates",
            ];

            foreach ($channels as $channel) {
                Redis::publish($channel, json_encode($data));
            }

        } catch (\Exception $e) {
            Log::error("Failed to notify user", [
                'user_id' => $userId,
                'error' => $e->getMessage(),
            ]);
        }
    }
}

