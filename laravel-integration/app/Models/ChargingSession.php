<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class ChargingSession extends Model
{
    /**
     * The table associated with the model.
     *
     * @var string
     */
    protected $table = 'charging_sessions';

    /**
     * The attributes that are mass assignable.
     *
     * @var array<int, string>
     */
    protected $fillable = [
        'user_id',
        'charger_id',
        'gun_id',
        'status',
        'started_at',
        'stopped_at',
        'python_cms_message_id',
        'transaction_id',
        'energy_delivered',
        'cost',
        'duration',
    ];

    /**
     * The attributes that should be cast.
     *
     * @var array<string, string>
     */
    protected $casts = [
        'started_at' => 'datetime',
        'stopped_at' => 'datetime',
        'energy_delivered' => 'float',
        'cost' => 'float',
        'duration' => 'integer',
    ];

    /**
     * Get the user that owns the charging session.
     */
    public function user(): BelongsTo
    {
        return $this->belongsTo(User::class);
    }

    /**
     * Get the charger associated with the session.
     */
    public function charger(): BelongsTo
    {
        return $this->belongsTo(Charger::class);
    }
}

