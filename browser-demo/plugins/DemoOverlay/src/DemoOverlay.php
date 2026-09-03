<?php
/*
 * Copyright 2026 shopware AG
 * SPDX-License-Identifier: MIT
 */

declare(strict_types=1);

namespace CommerceAgents\DemoOverlay;

use Shopware\Core\Framework\Plugin;

/**
 * Twig-only plugin: extends the storefront base layout and the administration index
 * with the demo launcher (Resources/views). No services, no migrations, no asset build —
 * it must install inside PHP WASM where neither Composer nor the theme compiler runs.
 */
class DemoOverlay extends Plugin
{
}
