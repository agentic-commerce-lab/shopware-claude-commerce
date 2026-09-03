<?php declare(strict_types=1);

namespace Swag\CommerceAgentTools\Tests\Unit\StagedChange;

use PHPUnit\Framework\Attributes\CoversClass;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\MockObject\MockObject;
use PHPUnit\Framework\TestCase;
use Shopware\Core\Content\Product\ProductCollection;
use Shopware\Core\Framework\Context;
use Shopware\Core\Framework\DataAbstractionLayer\DefinitionInstanceRegistry;
use Shopware\Core\Framework\DataAbstractionLayer\EntityRepository;
use Shopware\Core\Framework\DataAbstractionLayer\Event\EntityWrittenContainerEvent;
use Shopware\Core\Framework\DataAbstractionLayer\Search\Criteria;
use Shopware\Core\Framework\DataAbstractionLayer\Search\EntitySearchResult;
use Shopware\Core\Framework\Event\NestedEventCollection;
use Shopware\Core\Framework\Uuid\Uuid;
use Shopware\Core\System\SystemConfig\SystemConfigService;
use Swag\CommerceAgentTools\Event\AgentChangeAppliedEvent;
use Swag\CommerceAgentTools\Event\AgentChangeStagedEvent;
use Swag\CommerceAgentTools\StagedChange\ActorResolver;
use Swag\CommerceAgentTools\StagedChange\ChangeKind;
use Swag\CommerceAgentTools\StagedChange\ChangePlan;
use Swag\CommerceAgentTools\StagedChange\ChangeStatus;
use Swag\CommerceAgentTools\StagedChange\Entity\AgentStagedChangeCollection;
use Swag\CommerceAgentTools\StagedChange\Entity\AgentStagedChangeEntity;
use Swag\CommerceAgentTools\StagedChange\StagedChangeException;
use Swag\CommerceAgentTools\StagedChange\StagedChangeService;
use Swag\CommerceAgentTools\StagedChange\StagedChangeStateMachine;
use Swag\CommerceAgentTools\StagedChange\StageRequest;
use Swag\CommerceAgentTools\Tests\Unit\Support\ChangeFixtures;
use Symfony\Component\EventDispatcher\EventDispatcher;

/**
 * @internal
 */
#[CoversClass(StagedChangeService::class)]
#[CoversClass(ActorResolver::class)]
#[CoversClass(AgentStagedChangeEntity::class)]
#[CoversClass(StageRequest::class)]
class StagedChangeServiceTest extends TestCase
{
    /** @var EntityRepository<AgentStagedChangeCollection>&MockObject */
    private EntityRepository $changeRepository;

    /** @var EntityRepository<ProductCollection>&MockObject */
    private EntityRepository $productRepository;

    private EventDispatcher $dispatcher;

    /** @var list<object> */
    private array $dispatched = [];

    private SystemConfigService&MockObject $systemConfig;

    protected function setUp(): void
    {
        $this->changeRepository = $this->getMockBuilder(EntityRepository::class)->disableOriginalConstructor()->getMock();
        $this->productRepository = $this->getMockBuilder(EntityRepository::class)->disableOriginalConstructor()->getMock();
        $this->dispatcher = new EventDispatcher();
        $this->dispatched = [];
        $this->dispatcher->addListener(AgentChangeStagedEvent::EVENT_NAME, fn (object $event) => $this->dispatched[] = $event);
        $this->dispatcher->addListener(AgentChangeAppliedEvent::EVENT_NAME, fn (object $event) => $this->dispatched[] = $event);
        $this->systemConfig = $this->createMock(SystemConfigService::class);
        $this->systemConfig->method('getString')->willReturnMap([
            [StagedChangeService::CONFIG_APPROVER_EMAIL, null, 'approver@example.com'],
            [StagedChangeService::CONFIG_APPROVER_NAME, null, 'Ops Team'],
        ]);
    }

    public function testStageRecordsLedgerRowWithoutTouchingProductsAndDispatchesEvent(): void
    {
        $context = ChangeFixtures::adminContext([]);
        $change = ChangeFixtures::change();
        // The service generates the ID; echo it back from the mocked read.
        $this->changeRepository->method('search')->willReturnCallback(
            static function (Criteria $criteria) use ($context): EntitySearchResult {
                $ids = $criteria->getIds();
                $id = \is_string($ids[0] ?? null) ? $ids[0] : ChangeFixtures::CHANGE_ID;

                return ChangeFixtures::searchResult($context, ChangeFixtures::change(ChangeStatus::Staged, $id));
            },
        );

        $this->changeRepository->expects($this->once())->method('create')->with(
            $this->callback(static function (array $payload): bool {
                $row = $payload[0];

                return $row['kind'] === 'inventory_action'
                    && $row['status'] === 'staged'
                    && $row['targetEntity'] === 'product'
                    && $row['payload'] === [['id' => ChangeFixtures::PRODUCT_ID, 'stock' => 28]]
                    && $row['createdBy'] === ChangeFixtures::INTEGRATION_ID
                    && $row['createdByKind'] === 'integration'
                    && $row['summary'] === 'Restock stool by 25'
                    && $row['currency'] === 'EUR'
                    && $row['marginAfterPct'] === 31.5;
            }),
            $context,
        );
        $this->productRepository->expects($this->never())->method('upsert');
        $this->productRepository->expects($this->never())->method('update');

        $plan = new ChangePlan(ChangeKind::InventoryAction, 'product', [['id' => ChangeFixtures::PRODUCT_ID, 'stock' => 28]], [
            ['target' => ChangeFixtures::PRODUCT_ID, 'targetLabel' => 'Hocker', 'field' => 'stock', 'before' => 3, 'after' => 28],
        ]);
        $request = new StageRequest('Restock stool by 25', null, $change->getItems(), null, null, 'EUR', 20.0, 31.5, 15.0);

        $staged = $this->service()->stage($plan, $request, $context);

        static::assertTrue(Uuid::isValid($staged->getId()));
        static::assertCount(1, $this->dispatched);
        $event = $this->dispatched[0];
        static::assertInstanceOf(AgentChangeStagedEvent::class, $event);
        static::assertSame('swag.agent.change.staged', $event->getName());
        static::assertSame(['approver@example.com' => 'Ops Team'], $event->getMailStruct()->getRecipients());
        static::assertSame(ChangeFixtures::INTEGRATION_ID, $event->getActorId());
        static::assertSame('integration', $event->getActorKind());
        static::assertSame('inventory_action', $event->getValues()['kind']);
        static::assertSame(1, $event->getValues()['itemCount']);
    }

    public function testApplyWritesPayloadStampsUserAndDispatchesAppliedEvent(): void
    {
        $context = ChangeFixtures::adminContext([], ChangeFixtures::USER_ID, null);
        $staged = ChangeFixtures::change();
        $applied = ChangeFixtures::change(ChangeStatus::Applied);
        $applied->setAppliedBy(ChangeFixtures::USER_ID);
        $this->changeRepository->method('search')->willReturn(ChangeFixtures::searchResult($context, $applied));

        $this->productRepository->expects($this->once())->method('upsert')
            ->with([['id' => ChangeFixtures::PRODUCT_ID, 'stock' => 28]], $context)
            ->willReturn($this->writtenEvent($context));

        $this->changeRepository->expects($this->once())->method('update')->with(
            $this->callback(static fn (array $payload): bool => $payload[0]['id'] === ChangeFixtures::CHANGE_ID
                && $payload[0]['status'] === 'applied'
                && $payload[0]['appliedBy'] === ChangeFixtures::USER_ID
                && $payload[0]['appliedAt'] instanceof \DateTimeImmutable
                && $payload[0]['errorMessage'] === null),
            $context,
        );

        $result = $this->service()->apply($staged, $context);

        static::assertSame('applied', $result->getStatus());
        static::assertCount(1, $this->dispatched);
        static::assertInstanceOf(AgentChangeAppliedEvent::class, $this->dispatched[0]);
        static::assertSame('swag.agent.change.applied', $this->dispatched[0]->getName());
        static::assertSame('user', $this->dispatched[0]->getActorKind());
    }

    #[DataProvider('terminalStatusProvider')]
    public function testApplyRefusesChangesThatAreNotStaged(ChangeStatus $status): void
    {
        $context = ChangeFixtures::adminContext([]);
        $this->productRepository->expects($this->never())->method('upsert');
        $this->changeRepository->expects($this->never())->method('update');

        $this->expectException(StagedChangeException::class);
        $this->expectExceptionCode(StagedChangeException::CODE_INVALID_TRANSITION);

        $this->service()->apply(ChangeFixtures::change($status), $context);
    }

    #[DataProvider('terminalStatusProvider')]
    public function testDiscardRefusesChangesThatAreNotStaged(ChangeStatus $status): void
    {
        $context = ChangeFixtures::adminContext([]);
        $this->changeRepository->expects($this->never())->method('update');

        $this->expectException(StagedChangeException::class);
        $this->expectExceptionCode(StagedChangeException::CODE_INVALID_TRANSITION);

        $this->service()->discard(ChangeFixtures::change($status), $context);
    }

    /**
     * @return iterable<string, array{ChangeStatus}>
     */
    public static function terminalStatusProvider(): iterable
    {
        yield 'applied' => [ChangeStatus::Applied];
        yield 'discarded' => [ChangeStatus::Discarded];
    }

    public function testApplyRecordsWriteFailureAndKeepsStatusStaged(): void
    {
        $context = ChangeFixtures::adminContext([]);
        $this->productRepository->method('upsert')->willThrowException(new \RuntimeException('stock must be >= 0'));

        $this->changeRepository->expects($this->once())->method('update')->with(
            $this->callback(static fn (array $payload): bool => $payload[0] === ['id' => ChangeFixtures::CHANGE_ID, 'errorMessage' => 'stock must be >= 0']),
            $context,
        );

        try {
            $this->service()->apply(ChangeFixtures::change(), $context);
            static::fail('exception expected');
        } catch (\RuntimeException $e) {
            static::assertSame('stock must be >= 0', $e->getMessage());
        }

        static::assertSame([], $this->dispatched);
    }

    public function testDiscardStampsActorAndDoesNotWriteProducts(): void
    {
        $context = ChangeFixtures::adminContext([]);
        $discarded = ChangeFixtures::change(ChangeStatus::Discarded);
        $this->changeRepository->method('search')->willReturn(ChangeFixtures::searchResult($context, $discarded));
        $this->productRepository->expects($this->never())->method('upsert');

        $this->changeRepository->expects($this->once())->method('update')->with(
            $this->callback(static fn (array $payload): bool => $payload[0]['status'] === 'discarded'
                && $payload[0]['discardedBy'] === ChangeFixtures::INTEGRATION_ID
                && $payload[0]['discardedAt'] instanceof \DateTimeImmutable),
            $context,
        );

        $result = $this->service()->discard(ChangeFixtures::change(), $context);

        static::assertSame('discarded', $result->getStatus());
        static::assertSame([], $this->dispatched);
    }

    public function testFindThrowsForUnknownChange(): void
    {
        $context = ChangeFixtures::adminContext([]);
        $this->changeRepository->method('search')->willReturn(ChangeFixtures::searchResult($context));

        $this->expectException(StagedChangeException::class);
        $this->expectExceptionCode(StagedChangeException::CODE_NOT_FOUND);

        $this->service()->find(ChangeFixtures::CHANGE_ID, $context);
    }

    public function testActorFallsBackToSystemWithoutAdminSource(): void
    {
        $actor = (new ActorResolver())->resolve(Context::createDefaultContext());

        static::assertSame(['id' => 'system', 'kind' => 'system'], $actor);
    }

    public function testToolArrayExposesPreviewAsItems(): void
    {
        $data = ChangeFixtures::change()->toToolArray();

        static::assertSame(ChangeFixtures::CHANGE_ID, $data['changeId']);
        static::assertSame('staged', $data['status']);
        static::assertSame(1, $data['itemCount']);
        static::assertSame('stock', $data['items'][0]['field']);
        static::assertArrayNotHasKey('payload', $data);
        static::assertArrayHasKey('payload', ChangeFixtures::change()->toToolArray(true));
    }

    private function service(): StagedChangeService
    {
        $registry = $this->createMock(DefinitionInstanceRegistry::class);
        $registry->method('getRepository')->with('product')->willReturn($this->productRepository);

        return new StagedChangeService(
            $this->changeRepository,
            $registry,
            new StagedChangeStateMachine(),
            new ActorResolver(),
            $this->dispatcher,
            $this->systemConfig,
        );
    }

    private function writtenEvent(Context $context): EntityWrittenContainerEvent
    {
        return new EntityWrittenContainerEvent($context, new NestedEventCollection([]), []);
    }
}
