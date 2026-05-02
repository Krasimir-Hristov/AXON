import LoginButton from '@/features/auth/components/LoginButton';

const LoginPage = () => {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-gray-50">
      <div className="flex flex-col items-center gap-8 rounded-2xl bg-white p-12 shadow-lg">
        <div className="flex flex-col items-center gap-2">
          <h1 className="text-3xl font-bold tracking-tight text-gray-900">
            AXON
          </h1>
          <p className="text-sm text-gray-500">Your AI Personal Assistant</p>
        </div>
        <LoginButton />
      </div>
    </main>
  );
};

export default LoginPage;
