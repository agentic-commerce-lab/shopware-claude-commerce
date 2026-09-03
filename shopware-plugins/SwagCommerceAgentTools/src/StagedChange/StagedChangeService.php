<?php declare(strict_types=1);

namespace Swag\CommerceAgentTools\StagedChange;

use Shopware\Core\Framework\Context;
use Shopware\Core\Framework\DataAbstractionLayer\DefinitionInstanceRegistry;
use Shopware\Core\Framework\DataAbstractionLayer\EntityRepository;
use Shopware\Core\Framework\DataAbstractionLayer\Event\EntityWrittenContainerEvent;
use Shopware\Core\Framework\DataAbstractionLayer\Search\Criteria;
use Shopware\Core\Framework\DataAbstractionLayer\Search\EntitySearchResult;
use Shopware\Core\Framework\DataAbstractionLayer\Search\Filter\EqualsFilter;
use Shopware\Core\Framework\DataAbstractionLayer\Search\Sorting\FieldSorting;
use Shopware\Core\Framework\Uuid\Uuid;
use Shopware\Core\System\SystemConfig\SystemConfigService;
use Swag\CommerceAgentTools\Event\AgentChangeAppliedEvent;
use Swag\CommerceAgentTools\Event\AgentChangeStagedEvent;
use Swag\CommerceAgentTools\StagedChange\Entity\AgentStagedChangeCollection;
use Swag\CommerceAgentTools\StagedChange\Entity\AgentStagedChangeEntity;
use Symfony\Contracts\EventDispatcher\EventDispatcherInterface;

/**
 * Persists the ledger and executes the stage → apply / discard workflow.
 *
 * Staging never writes to the live catalog. Applying writes exactly the payload
 * that was previewed, through the DAL, with the caller's ACL context. Both
 * transitions are guarded by the state machine and stamp the acting principal.
 */
class StagedChangeService
{
    public const CONFIG_APPROVER_EMAIL = 'SwagCommerceAgentTools.config.approverEmail';
    public const CONFIG_APPROVER_NAME = 'SwagCommerceAgentTools.config.approverName';
    public const CONFIG_MAX_ITEMS = 'SwagCommerceAgentTools.config.maxItemsPerChange';
    public const DEFAULT_MAX_ITEMS = 50;

    /**
     * @param EntityRepository<AgentStagedChangeCollection> $changeRepository
     */
    public function __construct(
        private readonly EntityRepository $changeRepository,
        private readonly DefinitionInstanceRegistry $registry,
        private readonly StagedChangeStateMachine $stateMachine,
        private readonly ActorResolver $actorResolver,
        private readonly EventDispatcherInterface $eventDispatcher,
        private readonly SystemConfigService $systemConfig,
    ) {
    }

    public function maxItemsPerChange(): int
    {
        $configured = $this->systemConfig->getInt(self::CONFIG_MAX_ITEMS);

        return $configured > 0 ? $configured : self::DEFAULT_MAX_ITEMS;
    }

    /**
     * Records a planned change. Nothing is written to the target entity.
     */
    public function stage(ChangePlan $plan, StageRequest $request, Context $context): AgentStagedChangeEntity
    {
        $actor = $this->actorResolver->resolve($context);
        $id = Uuid::randomHex();

        $this->changeRepository->create([[
            'id' => $id,
            'kind' => $plan->kind->value,
            'status' => ChangeStatus::Staged->value,
            'summary' => $request->summary,
            'note' => $request->note,
            'targetEntity' => $plan->targetEntity,
            'items' => $request->items,
            'payload' => $plan->payload,
            'preview' => $plan->preview,
            'guardrailNotes' => $request->guardrailNotes,
            'createdBy' => $actor['id'],
            'createdByKind' => $actor['kind'],
            'salesChannelId' => $request->salesChannelId,
            'currency' => $request->currency,
            'marginBeforePct' => $request->marginBeforePct,
            'marginAfterPct' => $request->marginAfterPct,
            'minMarginPct' => $request->minMarginPct,
        ]], $context);

        $change = $this->find($id, $context);

        $this->eventDispatcher->dispatch(
            new AgentChangeStagedEvent($change, $context, $actor['id'], $actor['kind'], $this->mailRecipients()),
            AgentChangeStagedEvent::EVENT_NAME,
        );

        return $change;
    }

    /**
     * @throws StagedChangeException when the change does not exist
     */
    public function find(string $changeId, Context $context): AgentStagedChangeEntity
    {
        $change = $this->changeRepository->search(new Criteria([$changeId]), $context)->getEntities()->get($changeId);
        if (!$change instanceof AgentStagedChangeEntity) {
            throw StagedChangeException::notFound($changeId);
        }

        return $change;
    }

    /**
     * @return EntitySearchResult<AgentStagedChangeCollection>
     */
    public function list(?ChangeStatus $status, int $limit, int $page, Context $context): EntitySearchResult
    {
        $criteria = new Criteria();
        $criteria->setLimit($limit);
        $criteria->setOffset(($page - 1) * $limit);
        $criteria->setTotalCountMode(Criteria::TOTAL_COUNT_MODE_EXACT);
        $criteria->addSorting(new FieldSorting('createdAt', FieldSorting::DESCENDING));
        if ($status !== null) {
            $criteria->addFilter(new EqualsFilter('status', $status->value));
        }

        return $this->changeRepository->search($criteria, $context);
    }

    /**
     * Writes the previewed payload to the target entity. Used both for the
     * rolled-back dry-run preview and for the real apply.
     */
    public function executeWrite(AgentStagedChangeEntity $change, Context $context): EntityWrittenContainerEvent
    {
        return $this->write($change->getTargetEntity(), $change->getPayload(), $context);
    }

    /**
     * Writes a not-yet-recorded plan; only meaningful inside a rolled-back dry-run.
     */
    public function executePlan(ChangePlan $plan, Context $context): EntityWrittenContainerEvent
    {
        return $this->write($plan->targetEntity, $plan->payload, $context);
    }

    /**
     * @param list<array<string, mixed>> $payload
     */
    private function write(string $targetEntity, array $payload, Context $context): EntityWrittenContainerEvent
    {
        return $this->registry->getRepository($targetEntity)->upsert($payload, $context);
    }

    /**
     * @throws StagedChangeException when the change is not in status "staged"
     * @throws \Throwable when the live write fails; the failure is recorded on the change and the status stays "staged"
     */
    public function apply(AgentStagedChangeEntity $change, Context $context): AgentStagedChangeEntity
    {
        $this->stateMachine->assertTransition($change->getId(), ChangeStatus::from($change->getStatus()), ChangeStatus::Applied);
        $actor = $this->actorResolver->resolve($context);

        try {
            $this->executeWrite($change, $context);
        } catch (\Throwable $e) {
            $this->changeRepository->update([[
                'id' => $change->getId(),
                'errorMessage' => mb_substr($e->getMessage(), 0, 4000),
            ]], $context);

            throw $e;
        }

        $this->changeRepository->update([[
            'id' => $change->getId(),
            'status' => ChangeStatus::Applied->value,
            'appliedBy' => $actor['id'],
            'appliedAt' => new \DateTimeImmutable(),
            'errorMessage' => null,
        ]], $context);

        $applied = $this->find($change->getId(), $context);

        $this->eventDispatcher->dispatch(
            new AgentChangeAppliedEvent($applied, $context, $actor['id'], $actor['kind'], $this->mailRecipients()),
            AgentChangeAppliedEvent::EVENT_NAME,
        );

        return $applied;
    }

    /**
     * @throws StagedChangeException when the change is not in status "staged"
     */
    public function discard(AgentStagedChangeEntity $change, Context $context): AgentStagedChangeEntity
    {
        $this->stateMachine->assertTransition($change->getId(), ChangeStatus::from($change->getStatus()), ChangeStatus::Discarded);
        $actor = $this->actorResolver->resolve($context);

        $this->changeRepository->update([[
            'id' => $change->getId(),
            'status' => ChangeStatus::Discarded->value,
            'discardedBy' => $actor['id'],
            'discardedAt' => new \DateTimeImmutable(),
        ]], $context);

        return $this->find($change->getId(), $context);
    }

    /**
     * @return array<string, string>
     */
    private function mailRecipients(): array
    {
        $email = trim($this->systemConfig->getString(self::CONFIG_APPROVER_EMAIL));
        if ($email === '' || filter_var($email, \FILTER_VALIDATE_EMAIL) === false) {
            return [];
        }

        $name = trim($this->systemConfig->getString(self::CONFIG_APPROVER_NAME));

        return [$email => $name !== '' ? $name : $email];
    }
}
