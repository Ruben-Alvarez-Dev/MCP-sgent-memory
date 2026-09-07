# Specs — retention (capacidad nueva)

## TIER-01 — Clase de persistencia explícita

**Given** cualquier memoria capturada,
**When** se almacena,
**Then** lleva `persistence` ∈ {ephemeral, durable} — derivada: durables son
(i) notas destiladas en la KB, (ii) decisiones, (iii) importances ≥ umbral de
promoción, (iv) marca explícita del usuario; todo lo demás = ephemeral.
El derivado es determinista y auditable.
Test: `test_tier_default_ephemeral_and_derivations`

## TIER-02 — Durable jamás expira

**Given** una memoria durable,
**When** corre el reaper o cualquier barrido de retención,
**Then** es intocable: ni decay ni expiración; solo operación quirúrgica
con trace (SURG) o decisión humana explícita.
Test: `test_reaper_never_touches_durable`

## TIER-03 — Decay Ebbinghaus de efímeras

**Given** una memoria ephemeral no recordada desde t₀ con importance I₀,
**When** pasa el tiempo,
**Then** su importancia efectiva es I₀·e^(-Δt/S) con estabilidad
S = S₀·(1+reinforce_count) — el recall REFORZA (spaced repetition: ser
recordado protege de olvidar).
Test: `test_decay_curve_and_reinforcement`

## TIER-04 — Expiración: archivo antes que borrado

**Given** una efímera con importancia efectiva < umbral de olvido,
**When** corre el reaper,
**Then** se archiva completa (bundle JSONL con traza L0 "forgotten") y se
elimina de points/FTS (el contenido se olvida, el HECHO de haber olvidado
persiste) — restaurable por undo quirúrgico.
Test: `test_expiry_archives_then_forgets`

## TIER-05 — La destilación protege la fuente

**Given** una efímera cuya verdad fue destilada a la KB (nota verificada o
pulido-agente con source: memory:<id>),
**When** su contenido crudo expire,
**Then** expira SIN pérdida de conocimiento (la verdad vive en la KB) y el
evento de archivo lo registra como `distilled=true`.
Test: `test_distilled_source_expires_without_loss`

## TIER-06 — Bi-temporalidad solo en durables

**Given** un hecho durable que deja de ser cierto ("el deploy actual es X"),
**When** se registra la nueva verdad,
**Then** el viejo se marca invalid_at (sigue consultable histórico, filtrable)
— nunca borrado silencioso.
Test: `test_durable_facts_expire_by_validity_not_deletion`

## TIER-07 — Olvidar es observable

**Given** cualquier expiración o decay,
**When** ocurre,
**Then** L0 recibe evento `forgotten {memory_id, clase, razón, distillated}`
y la UI expone un informe de retención (olvidadas/periodo, restaurables).
Test: `test_forgetting_is_observable`

## TIER-08 — Override del humano

**Given** el usuario marca cualquier memoria como durable (o le pone TTL),
**When** el reaper corre,
**Then** la marca gana sobre cualquier derivación automática.
Test: `test_user_override_wins`
