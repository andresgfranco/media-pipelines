# 🚀 Deploy Streamlit Dashboard to Internet

Hay varias opciones para desplegar tu dashboard de Streamlit en internet. Aquí están las más recomendadas:

## Opción 1: Streamlit Community Cloud (⭐ Recomendado - Más Fácil)

**Gratis y muy fácil de configurar. Solo necesitas GitHub.**

### Pasos:

1. **Sube tu código a GitHub** (si no lo has hecho):
   ```bash
   git remote add origin <tu-repo-url>
   git push -u origin main
   ```

2. **Ve a [share.streamlit.io](https://share.streamlit.io)**

3. **Conecta tu cuenta de GitHub**

4. **Selecciona tu repositorio** (`media-pipelines`)

5. **Configura la aplicación**:
   - **Main file path**: `dashboard/app.py`
   - **Python version**: `3.11`

6. **Configura las Secrets** (variables de entorno):
   - Ve a "Advanced settings" → "Secrets"
   - Agrega estas variables:
     ```toml
     AWS_ACCESS_KEY_ID = "tu-access-key"
     AWS_SECRET_ACCESS_KEY = "tu-secret-key"
     AWS_DEFAULT_REGION = "us-east-1"
     MEDIA_PIPELINES_VIDEO_STATE_MACHINE_ARN = "arn:aws:states:..."
     MEDIA_PIPELINES_VIDEO_BUCKET = "media-pipelines-video-..."
     MEDIA_PIPELINES_METADATA_TABLE = "media-pipelines-metadata"
     MEDIA_PIPELINES_AWS_REGION = "us-east-1"
     ```

7. **Deploy!** Tu app estará disponible en `https://tu-app.streamlit.app`

### Ventajas:
- ✅ Gratis
- ✅ Muy fácil de configurar
- ✅ Auto-deploy cuando haces push a GitHub
- ✅ HTTPS automático
- ✅ Sin necesidad de servidor

---

## Opción 2: AWS App Runner (Integrado con AWS)

**Más control y mejor integración con tu infraestructura AWS existente.**

### Prerequisitos:
- Docker instalado
- AWS CLI configurado

### Pasos:

1. **Crea un Dockerfile** (ya está creado en `Dockerfile.streamlit`)

2. **Construye y sube la imagen a ECR**:
   ```bash
   # Crear repositorio ECR
   aws ecr create-repository --repository-name media-pipelines-streamlit --region us-east-1

   # Obtener login token
   aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com

   # Construir imagen
   docker build -f Dockerfile.streamlit -t media-pipelines-streamlit .

   # Taggear
   docker tag media-pipelines-streamlit:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/media-pipelines-streamlit:latest

   # Subir
   docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/media-pipelines-streamlit:latest
   ```

3. **Crea el servicio App Runner**:
   ```bash
   # Usa la consola de AWS o crea un archivo apprunner.yaml
   ```

4. **Configura variables de entorno en App Runner** (igual que Streamlit Cloud)

### Ventajas:
- ✅ Integrado con AWS
- ✅ Escalable automáticamente
- ✅ Más control sobre recursos

---

## Opción 3: AWS Fargate (ECS)

**Para deployments más complejos o si necesitas más control.**

Ver `docs/streamlit-deploy.md` para instrucciones detalladas.

---

## ⚠️ Importante: Seguridad

**NUNCA subas tus credenciales de AWS al código:**

- ✅ Usa Secrets/Environment Variables en la plataforma de deployment
- ✅ Considera usar IAM Roles si es posible (App Runner/Fargate)
- ✅ Limita los permisos del IAM user/role solo a lo necesario

---

## 🧪 Probar Localmente Antes de Deployar

```bash
# Asegúrate de que funciona localmente primero
export AWS_ACCESS_KEY_ID=tu-key
export AWS_SECRET_ACCESS_KEY=tu-secret
export MEDIA_PIPELINES_VIDEO_STATE_MACHINE_ARN=tu-arn
# ... otras variables

streamlit run dashboard/app.py
```

---

## 📝 Checklist Pre-Deployment

- [ ] `requirements.txt` existe y tiene todas las dependencias
- [ ] Variables de entorno configuradas como secrets
- [ ] Dashboard funciona localmente con las variables de entorno
- [ ] Código subido a GitHub (para Streamlit Cloud)
- [ ] IAM permissions correctos para el dashboard

---

## 🆘 Troubleshooting

**"ModuleNotFoundError"**
- Verifica que `requirements.txt` tiene todas las dependencias
- Streamlit Cloud instala automáticamente desde `requirements.txt`

**"AWS credentials not found"**
- Verifica que configuraste los secrets correctamente
- En Streamlit Cloud, los secrets deben estar en formato TOML

**"State Machine ARN not configured"**
- Verifica que `MEDIA_PIPELINES_VIDEO_STATE_MACHINE_ARN` está en los secrets
