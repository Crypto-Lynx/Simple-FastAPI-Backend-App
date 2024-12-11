# libs
from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from database import engine, Base, get_db
from database import UserCreate, Token
from auth import create_access_token, get_current_user
from database import User, Room
from passlib.context import CryptContext

# Utils
# Hashing algorithm for passwords
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Function to hash passwords
def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

# Function to verify a hashed password
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)





app = FastAPI()
router = APIRouter()
app.include_router(router)
Base.metadata.create_all(bind=engine)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
#oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Root route
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, db: Session = Depends(get_db)):
    user_auth_status = False
    user_mail = None
    user_data = None
    try:
        user_data = get_current_user(request, db)
    except HTTPException:
        raise HTTPException
    else:
        user_auth_status = True
        user_mail = user_data.mail
        return templates.TemplateResponse("index.html", {"request": request, "status": user_auth_status, "user_mail": user_mail})


# Registration route
@app.get("/register", response_class=HTMLResponse)
async def get_register(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "title": "Register page"})

@app.post("/register", response_model=Token)
async def post_register(user: UserCreate, db: Session = Depends(get_db)):
    # Check if user already exists
    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Hash the password and create the user
    hashed_password = get_password_hash(user.password)
    new_user = User(email=user.email, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Generate JWT token
    access_token = create_access_token(data={"sub": new_user.email})
    return RedirectResponse(url="/login", status_code=303)

# Login route
@app.get("/login", response_class=HTMLResponse)
async def get_login(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "title": "Login page"})

@app.post("/login", response_model=Token)
async def post_login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Generate JWT token for authentication
    access_token = create_access_token(data={"sub": user.email})
    
    response = RedirectResponse(url="/me", status_code=303)
    response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=False, secure=True, samesite="Lax")
    return response

# User profile (protected)
@app.get("/me")
async def get_profile(current_user: User = Depends(get_current_user)):
    return {"message": f"Welcome to your cabinet, {current_user.email}!"}

# Logout (protected)
@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/")
    response.delete_cookie(key="Authorization")
    response.delete_cookie(key="user")

    return response

# Rooms route (protected)
@app.get("/rooms", response_class=HTMLResponse, )
async def get_rooms(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user_auth_status = False
    user_mail = None
    user_data = None
    rooms = []
    try:
        user_data = get_current_user(request, db)
    except HTTPException:
        raise HTTPException()
    else:
        user_auth_status = True
        user_mail = user_data.mail
        rooms = db.query(Room).filter(Room.owner_id == user_data.id).all()
        return templates.TemplateResponse("rooms.html", 
                                          {"request": request, "status": user_auth_status, "user_mail": user_mail, "rooms": rooms})

@app.post("/rooms", response_class=HTMLResponse)
async def create_room(name: str = Form(...), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    check_room = db.query(Room).filter(Room.name == name).first()
    
    if check_room:
        raise HTTPException(status_code=400, detail="Room with this name already exists")
    
    new_room = Room(name = name, owner_id = current_user.id)
    db.add(new_room)
    db.commit()
    db.refresh(new_room)
    return {"message": f"Chat room '{name}' created successfully"}


# Individual room route (protected)
@app.delete("/rooms/{room_id}")
async def delete_room(room_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    room = db.query(Room).filter(Room.id == room_id, Room.owner_id == current_user.id).first()
    
    if not room:
        raise HTTPException(status_code=404, detail="This room is not found or you don't have privileges to delete it")
    
    db.delete(room)
    db.commit()

    return {"message": f"Chat room '{room.name}' deleted successfully"}

@app.get("/rooms/{room_id}")
async def join_room(request: Request, room_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    room = db.query(Room).filter(Room.id == room_id).first()

    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")

    return templates.TemplateResponse("room.html", {"request": request, "room_name": room.name})