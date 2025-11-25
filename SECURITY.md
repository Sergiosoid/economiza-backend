# Segurança - Economiza Backend

Este documento descreve as medidas de segurança implementadas no backend do Economiza.

## Autenticação

### Supabase JWT

O backend valida tokens JWT do Supabase Auth usando JWKS (JSON Web Key Set).

**Configuração:**
```env
SUPABASE_JWKS_URL=https://<project>.supabase.co/.well-known/jwks.json
SUPABASE_AUDIENCE=<audience>
```

**Fluxo:**
1. Cliente autentica no Supabase e recebe JWT
2. Cliente envia JWT no header `Authorization: Bearer <token>`
3. Backend valida assinatura usando chaves públicas (JWKS)
4. Backend verifica `exp`, `aud` e outros claims
5. Backend busca ou cria usuário baseado no `sub` e `email` do token

**Cache de JWKS:**
- JWKS é cacheado por 1 hora
- Revalidação automática após expiração do cache

### JWT Interno

O backend gera tokens JWT internos para operações sensíveis (ex: links de exportação).

**Configuração:**
```env
JWT_SECRET=<secret-aleatorio>
JWT_ALGORITHM=HS256
JWT_EXPIRES_MIN=60
```

**Uso:**
```python
from app.utils.jwt_utils import create_internal_token, verify_internal_token

# Criar token
token = create_internal_token(user_id, expires_min=60)

# Verificar token
payload = verify_internal_token(token)
user_id = UUID(payload["user_id"])
```

### Modo Desenvolvimento

Em desenvolvimento, o token `"test"` é aceito se `DEV_MODE=true`:

```env
DEV_MODE=true
```

**⚠️ IMPORTANTE:** Em produção, `DEV_MODE` deve ser `false` ou não configurado.

## Rate Limiting

Rate limiting é implementado usando Redis com sliding window.

**Configuração:**
```env
REDIS_URL=redis://localhost:6379/0
RATE_LIMIT_PREFIX=economiza:
```

**Limites Aplicados:**
- `/api/v1/receipts/scan`: 10 req/min por usuário
- `/api/v1/analytics/*`: 30 req/min por usuário
- `/api/v1/user/*`: 5 req/min por usuário
- Limite global por IP: 100 req/min (futuro)

**Fallback:**
- Se Redis não estiver disponível em `DEV_MODE=true`, usa fallback in-memory
- Em produção, Redis é obrigatório

**Resposta:**
```json
{
  "detail": "rate limit exceeded"
}
```
Status: `429 Too Many Requests`

## Row Level Security (RLS)

RLS está habilitado no Supabase para proteger dados por usuário.

**Policies Aplicadas:**
- `receipts`: Usuários só veem/inserem/atualizam seus próprios receipts
- `receipt_items`: Baseado no `receipt.user_id`
- `analytics_cache`: Usuários só acessam seus próprios caches
- `products`: Leitura pública (produtos são compartilhados)

**Migration:**
```bash
alembic upgrade head
```

**⚠️ IMPORTANTE:** 
- RLS policies assumem que `auth.uid()` retorna o UUID do usuário
- Em desenvolvimento, pode ser necessário desabilitar RLS temporariamente
- Revisar policies antes de aplicar em produção

## Validação de QR Code

O endpoint `/api/v1/receipts/scan` valida e sanitiza QR codes antes de processar.

**Validações:**
- Tamanho máximo: 2000 caracteres
- Formato: URL (http/https) ou chave de acesso (44 dígitos)
- Bloqueio de padrões perigosos: `<script>`, `javascript:`, `data:text/html`, etc.
- Sanitização: Remove caracteres de controle, normaliza espaços

**Respostas:**
- `400 Bad Request`: QR code inválido ou perigoso
- Mensagens claras sobre o problema

## Stripe Webhooks

Webhooks do Stripe são validados usando assinatura HMAC.

**Configuração:**
```env
STRIPE_WEBHOOK_SECRET=whsec_...
```

**Validação:**
1. Extrai assinatura do header `stripe-signature`
2. Valida usando `stripe.Webhook.construct_event()`
3. Rejeita com `400 Bad Request` se assinatura inválida
4. Loga tentativas inválidas (possíveis ataques)

**Eventos Processados:**
- `checkout.session.completed`: Ativa assinatura PRO
- `customer.subscription.updated`: Atualiza status
- `customer.subscription.deleted`: Remove PRO

## Checklist de Deploy Seguro

### Antes do Deploy

- [ ] `DEV_MODE=false` ou não configurado
- [ ] `JWT_SECRET` configurado com valor aleatório forte
- [ ] `STRIPE_WEBHOOK_SECRET` configurado
- [ ] `SUPABASE_JWKS_URL` configurado corretamente
- [ ] `SUPABASE_AUDIENCE` configurado (se necessário)
- [ ] `REDIS_URL` configurado e acessível
- [ ] RLS policies revisadas e aplicadas
- [ ] Chaves e secrets não estão no repositório

### Após o Deploy

- [ ] Testar autenticação com token Supabase real
- [ ] Verificar rate limiting funcionando
- [ ] Testar webhook do Stripe com evento real
- [ ] Verificar logs de segurança
- [ ] Monitorar tentativas de acesso não autorizado

## Operação em Modo DEV

Para desenvolvimento local:

1. Configure `DEV_MODE=true` no `.env`
2. Use token `"test"` para autenticação
3. Redis é opcional (usa fallback in-memory)
4. RLS pode ser desabilitado temporariamente se necessário

**⚠️ NUNCA** use `DEV_MODE=true` em produção!

## Logs de Segurança

O backend loga:
- Tentativas de autenticação falhadas
- Rate limit excedido
- QR codes bloqueados
- Webhooks com assinatura inválida
- Tentativas de acesso não autorizado

Monitore os logs regularmente para detectar ataques ou problemas.

## Contato

Para reportar vulnerabilidades de segurança, entre em contato com a equipe de desenvolvimento.

