# AXON — Полезни команди

## Стартиране на Backend сървъра

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

---

## Git работен процес

### 1. Създай нов branch

```bash
git checkout -b feature/ime-na-bransha
```

### 2. Добави промените и направи commit

```bash
git add .
git commit -m "feat: описание на промените"
```

### 3. Push към GitHub

```bash
git push -u origin feature/ime-na-bransha
```

> След push — отвори GitHub, създай Pull Request и изчакай review.  
> Когато PR-ът бъде одобрен, merge-ни го от GitHub конзолата.

---

## След merge от GitHub

### 4. Върни се на main и дръпни промените

```bash
git checkout main
git pull origin main
```

### 5. Изтрий локалния branch

```bash
git branch -d feature/ime-na-bransha
```
