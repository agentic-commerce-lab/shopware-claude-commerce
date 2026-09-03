<?php declare(strict_types=1);

namespace Swag\CommerceAgentTools\StagedChange;

use Shopware\Core\Content\Product\ProductEntity;
use Shopware\Core\Framework\Context;
use Shopware\Core\Framework\DataAbstractionLayer\EntityRepository;
use Shopware\Core\Framework\DataAbstractionLayer\Pricing\Price;
use Shopware\Core\Framework\DataAbstractionLayer\Search\Criteria;

/**
 * Reads the products referenced by a change through the Admin DAL (ACL applies).
 */
class ProductSnapshotLoader
{
    /**
     * @param EntityRepository<\Shopware\Core\Content\Product\ProductCollection> $productRepository
     */
    public function __construct(
        private readonly EntityRepository $productRepository,
    ) {
    }

    /**
     * @param list<string> $productIds
     *
     * @return array<string, ProductSnapshot> keyed by product ID
     *
     * @throws StagedChangeException when at least one product does not exist
     */
    public function load(array $productIds, Context $context): array
    {
        if ($productIds === []) {
            return [];
        }

        $criteria = new Criteria(array_values(array_unique($productIds)));
        $criteria->addAssociation('tax');

        $snapshots = [];
        foreach ($this->productRepository->search($criteria, $context)->getEntities() as $product) {
            $snapshots[$product->getId()] = $this->snapshot($product);
        }

        $missing = array_values(array_diff($productIds, array_keys($snapshots)));
        if ($missing !== []) {
            throw StagedChangeException::productsMissing($missing);
        }

        return $snapshots;
    }

    private function snapshot(ProductEntity $product): ProductSnapshot
    {
        $listingFields = [];
        foreach (ChangePlanner::LISTING_FIELDS as $field) {
            $value = $product->getTranslation($field);
            $listingFields[$field] = \is_string($value) ? $value : null;
        }

        $prices = [];
        foreach ($product->getPrice() ?? [] as $price) {
            if (!$price instanceof Price) {
                continue;
            }
            $prices[$price->getCurrencyId()] = [
                'gross' => $price->getGross(),
                'net' => $price->getNet(),
                'linked' => $price->getLinked(),
            ];
        }

        return new ProductSnapshot(
            id: $product->getId(),
            productNumber: $product->getProductNumber(),
            listingFields: $listingFields,
            stock: $product->getStock(),
            active: $product->getActive() ?? false,
            taxRate: $product->getTax()?->getTaxRate() ?? 0.0,
            prices: $prices,
        );
    }
}
