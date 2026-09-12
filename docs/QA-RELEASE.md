# QA & Release Checklist

## Functional

- [ ] landing works
- [ ] demo works without credentials
- [ ] upload works
- [ ] invalid upload gives guidance
- [ ] style profile saves
- [ ] product selection works
- [ ] generation state works
- [ ] result renders
- [ ] remix works
- [ ] save works
- [ ] shop CTA works
- [ ] planner works where enabled
- [ ] failures can recover

## Responsive

- [ ] mobile 360px
- [ ] mobile 390px
- [ ] tablet
- [ ] desktop 1280px
- [ ] desktop 1440px+
- [ ] no horizontal overflow
- [ ] touch targets adequate

## Accessibility

- [ ] keyboard navigation
- [ ] focus states
- [ ] labels
- [ ] semantics
- [ ] contrast
- [ ] reduced motion

## Performance

- [ ] optimized images
- [ ] heavy components lazy-loaded
- [ ] no unnecessary rerender loops
- [ ] generation does not block UI
- [ ] cached demo result

## Security

- [ ] no secrets committed
- [ ] upload validation
- [ ] ownership checks
- [ ] no raw image logging
- [ ] provider errors sanitized

## Build gates

- [ ] formatting
- [ ] lint
- [ ] typecheck
- [ ] unit tests
- [ ] integration tests
- [ ] production build

## Portfolio gate

- [ ] README has product story
- [ ] architecture diagram
- [ ] screenshots
- [ ] demo path
- [ ] measured demo metrics clearly labelled as demo/experimental
- [ ] no false retailer affiliation claims
