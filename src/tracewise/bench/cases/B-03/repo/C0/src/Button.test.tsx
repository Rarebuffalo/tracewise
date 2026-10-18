import { render } from "@testing-library/react";
import { Button } from "./Button";

test("Button renders label", () => {





  const { container } = render(<Button label="Buy now" />);
  expect(container).toMatchSnapshot();
});
