<?php

declare(strict_types=1);

namespace CommerceAgents\Handoff\Storefront\Controller;

use Shopware\Core\PlatformRequest;
use Shopware\Storefront\Controller\StorefrontController;
use Shopware\Storefront\Framework\Routing\StorefrontRouteScope;
use Symfony\Component\HttpFoundation\Cookie;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\Routing\Attribute\Route;

/**
 * UCP carts are identified by the Store API context token. The shopping agent
 * cannot set that cookie on the Shopware origin, so this route adopts the token
 * into the storefront session and sends the shopper to checkout confirm.
 */
#[Route(defaults: [PlatformRequest::ATTRIBUTE_ROUTE_SCOPE => [StorefrontRouteScope::ID]])]
class ContinueController extends StorefrontController
{
    #[Route(path: '/claude-commerce/continue', name: 'frontend.claude_commerce.continue', methods: ['GET'])]
    public function continueCheckout(Request $request): Response
    {
        $token = $request->query->get('token');
        if (!\is_string($token) || !preg_match('/^[A-Za-z0-9_-]{16,128}$/', $token)) {
            return $this->redirectToRoute('frontend.checkout.cart.page');
        }

        if ($request->hasSession()) {
            $session = $request->getSession();
            $session->set(PlatformRequest::HEADER_CONTEXT_TOKEN, $token);
        }

        $response = $this->redirectToRoute('frontend.checkout.confirm.page');
        $response->headers->setCookie(
            Cookie::create(PlatformRequest::HEADER_CONTEXT_TOKEN, $token)
                ->withHttpOnly(true)
                ->withSameSite(Cookie::SAMESITE_LAX)
                ->withPath('/')
        );

        return $response;
    }
}
